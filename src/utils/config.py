"""Global config for the backend."""
import os
import logging

# We assume we are in dev, prod has to be set explicitly
if os.getenv('DEPLOY_MODE') == 'prod':
    cookie_options_samesite = "Strict"
    cookie_options_secure = True
    logging_level = logging.CRITICAL
    db_conn_str = 'sqlite:///prod.db'
else:
    cookie_options_samesite = "Lax"
    cookie_options_secure = False
    logging_level = logging.CRITICAL
    db_conn_str = 'sqlite:///test.db'
