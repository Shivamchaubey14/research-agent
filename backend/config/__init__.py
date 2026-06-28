# Use the pure-Python PyMySQL driver as a drop-in replacement for mysqlclient,
# so the project installs cleanly on Windows and in slim containers without
# needing MySQL C build tooling.
import pymysql

pymysql.install_as_MySQLdb()
