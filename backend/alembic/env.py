from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.config import settings
from app.database import Base
from app.foundation import models as foundation_models  # noqa: F401
from app.farm import models as farm_models  # noqa: F401
from app.gis import models as gis_models  # noqa: F401
from app.twins import models as twin_models  # noqa: F401
from app.iot import models as iot_models  # noqa: F401
from app.irrigation import models as irrigation_models  # noqa: F401
from app.weather import models as weather_models  # noqa: F401
from app.vision import models as vision_models  # noqa: F401
from app.crophealth import models as crophealth_models  # noqa: F401
from app.harvest import models as harvest_models  # noqa: F401
from app.asset import models as asset_models  # noqa: F401
from app.inventory import models as inventory_models  # noqa: F401
from app.accounting import models as accounting_models  # noqa: F401
from app.sales import models as sales_models  # noqa: F401
from app.ai import models as ai_models  # noqa: F401
from app import models as legacy_models  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
