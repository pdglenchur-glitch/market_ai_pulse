"""Resolves SQL warehouse connection details dynamically rather than hardcoding
a warehouse ID, since Databricks Free Edition provisions one serverless
warehouse per workspace ("Serverless Starter Warehouse").
"""
import os

from databricks import sql
from databricks.sdk import WorkspaceClient


def connect():
    client = WorkspaceClient(host=os.environ["DATABRICKS_HOST"], token=os.environ["DATABRICKS_TOKEN"])
    warehouses = list(client.warehouses.list())
    if not warehouses:
        raise RuntimeError("No SQL warehouses found in this workspace")
    warehouse = warehouses[0]

    return sql.connect(
        server_hostname=warehouse.odbc_params.hostname,
        http_path=warehouse.odbc_params.path,
        access_token=os.environ["DATABRICKS_TOKEN"],
    )
