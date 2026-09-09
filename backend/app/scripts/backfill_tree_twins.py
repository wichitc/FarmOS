"""Backfills `digital_twin_id` for any `Tree` row created before Phase 6
landed (every tree-creation path in `routers/v1/farm.py` now creates its
twin inline, but pre-existing trees need a one-off catch-up).

Usage: python -m app.scripts.backfill_tree_twins <tenant_slug>
"""
import sys

from ..core.deps import set_tenant_context
from ..database import SessionLocal
from ..farm import models as farm_models
from ..foundation import models as fm
from ..twins.service import create_twin, get_or_create_twin_type

TREE_TWIN_TYPE_CODE = "tree"


def _farm_id_for_tree(db, tree: farm_models.Tree) -> str:
    row = db.get(farm_models.Row, tree.row_id)
    block = db.get(farm_models.Block, row.block_id)
    plot = db.get(farm_models.Plot, block.plot_id)
    zone = db.get(farm_models.Zone, plot.zone_id)
    return zone.farm_id


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        raise SystemExit(1)
    slug = sys.argv[1]

    db = SessionLocal()
    try:
        tenant = db.query(fm.Tenant).filter(fm.Tenant.slug == slug).one_or_none()
        if tenant is None:
            print(f"No tenant with slug '{slug}'")
            raise SystemExit(1)
        set_tenant_context(db, tenant.id)

        trees = (
            db.query(farm_models.Tree)
            .filter(farm_models.Tree.digital_twin_id.is_(None))
            .all()
        )
        if not trees:
            print(f"Nothing to backfill for tenant '{slug}'.")
            return

        twin_type = get_or_create_twin_type(db, tenant.id, code=TREE_TWIN_TYPE_CODE, name="Tree", category="tree")
        for tree in trees:
            twin = create_twin(
                db,
                tenant_id=tenant.id,
                twin_type=twin_type,
                display_code=tree.code,
                farm_id=_farm_id_for_tree(db, tree),
                current_state={"growth_stage": tree.growth_stage},
            )
            tree.digital_twin_id = twin.id

        db.commit()
        print(f"Backfilled {len(trees)} tree twin(s) for tenant '{slug}'.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
