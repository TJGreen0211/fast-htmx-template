import argparse
from src.utils.db_model.mgmt.utility import DBUtility

from src.models.user import Role, Registration, User, UserMeta


def migrate(refresh=False):
    print(f"Migrating database with args: {refresh}")
    DBUtility.migrate(Role, drop_table=refresh)
    DBUtility.migrate(Registration, drop_table=refresh)
    DBUtility.migrate(User, drop_table=refresh)
    DBUtility.migrate(UserMeta, drop_table=refresh)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", help="Drop and recreate the databases", action='store_true')
    args = parser.parse_args()

    migrate(refresh=args.refresh)
