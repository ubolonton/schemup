# TODO: Base class for this & PostgresSchema
class MysqlSchema(object):

    def __init__(self, conn, dryRun=False):
        self.conn = conn
        self.dryRun = dryRun
        self.runLog = []


    def execute(self, query, args=(), cur=None, log=True):
        if cur is None:
            cur = self.conn.cursor()

        # Run first
        if not self.dryRun:
            cur.execute(query, args)

        # If ok log
        if log:
            # FIX: possible unicode problems and other
            if args:
                self.runLog.append("%s [%s]\n" % (query, ", ".join(map(str, args))))
            else:
                self.runLog.append(query)

    def flushLog(self):
        log, self.runLog = self.runLog, []
        return log

    def printLog(self):
        for line in self.flushLog():
            print line

    # TODO
    def begin(self):
        if self.dryRun:
            self.runLog.append("START TRANSACTION")

    # TODO
    def commit(self):
        if self.dryRun:
            self.runLog.append("COMMIT")
        else:
            self.conn.commit()

    def ensureSchemaTable(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT COUNT(*)"
            " FROM `information_schema`.`tables`"
            " WHERE `table_name` = 'schemup_tables'")

        if cur.fetchone()[0]:
            return

        print "Creating schema table..."
        cur.execute(
            "CREATE TABLE `schemup_tables` ("
            " `table_name` VARCHAR(255) NOT NULL,"
            " `version` VARCHAR(255) NOT NULL,"
            " `is_current` TINYINT(1) NOT NULL DEFAULT 0,"
            " `schema` TEXT)")

        self.conn.commit()

    def clearSchemaTable(self):
        self.execute("DELETE FROM `schemup_tables`")

    def getSchema(self, tableName):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT `column_name`, `data_type`, `is_nullable`, `column_default`"
            " FROM `information_schema`.`columns`"
            " WHERE `table_name` = %s"
            " ORDER BY `column_name`",
            (tableName,))

        return u"\n".join(u"|".join(unicode(c) for c in row) for row in cur)

    def getTableVersions(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT `table_name`, `version`"
            " FROM `schemup_tables`"
            " WHERE `is_current` = 1")
        return cur


    def getVersionedTableSchemas(self):
        cur = self.conn.cursor()
        cur.execute(
            "SELECT `table_name`, `schema`"
            " FROM `schemup_tables`"
            " WHERE `is_current` = 1")
        return cur


    def setSchema(self, tableName, version, log=True):

        schema = self.getSchema(tableName)

        cur = self.conn.cursor()
        self.execute(
            "UPDATE `schemup_tables`"
            " SET `is_current` = 0"
            " WHERE `table_name` = %s",
            (tableName,), cur, log)
        self.execute(
            "INSERT INTO `schemup_tables`"
            " (`table_name`, `version`, `is_current`, `schema`)"
            " VALUES (%s, %s, 1, %s)",
            (tableName, version, schema), cur, log)


    def getKnownTableVersions(self):
        self.ensureSchemaTable()

        cur = self.conn.cursor()
        cur.execute(
            "SELECT `table_name`, `version`"
            " FROM `schemup_tables`"
            " WHERE `is_current` = 1")

        return sorted(cur.fetchall())

    @classmethod
    def _parseColumnSchemaString(self, columnSchema):
        name, data_type, is_nullable, column_default = columnSchema.split("|")
        return name, {
            "data_type": data_type,
            "is_nullable": is_nullable,
            "column_default": column_default
        }

    @classmethod
    def _parseSchemaString(self, schema):
        result = {}
        columnSchemas = schema.split("\n")
        for c in columnSchemas:
            name, data = self._parseColumnSchemaString(c)
            result[name] = data
        return result

    @classmethod
    def formatMismatch(self, actualTableSchema, expectedTableSchema):
        result = []
        actual = self._parseSchemaString(actualTableSchema)
        expected = self._parseSchemaString(expectedTableSchema)

        actual_cols = set(actual.keys())
        expected_cols = set(expected.keys())

        for col in actual_cols.difference(expected_cols):
            result.append("Column `%s` not expected" % col)
        for col in expected_cols.difference(actual_cols):
            result.append("Column `%s` not found" % col)

        for col in (actual_cols.intersection(expected_cols)):
            actual_data = actual[col]
            expected_data = expected[col]
            for attr, msg in (
                ("data_type"      , "Column `%s`: found %s, expected %s"),
                ("is_nullable"    , "Column `%s`: nullable %s, expected %s"),
                ("column_default" , "Column `%s`: default %s, expected %s"),
            ):
                if actual_data.get(attr) != expected_data.get(attr):
                    result.append(msg % (col, actual_data.get(attr), expected_data.get(attr)))

        return "\n".join(result)
