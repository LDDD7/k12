"""
组织架构 DAO — 操作 sys_organization 表（SQLAlchemy ORM）
支持树形结构查询（区域 → 部门 → 组）
三维度权限过滤：self（仅本人所属组织）/ region（本区域全部）/ all（全部）
"""

from typing import Optional, List, Dict

from sqlalchemy import literal, select, delete, update

from k12_app.backend.dao.db import session_scope
from k12_app.backend.models import SysOrganization, SysEmployee


def _org_dict(r: SysOrganization) -> Dict:
    return {
        "org_id": r.org_id,
        "org_name": r.org_name,
        "parent_org_id": r.parent_org_id,
        "org_type": r.org_type,
        "wework_account_id": r.wework_account_id,
        "sort_order": r.sort_order,
    }


class OrganizationDAO:
    """组织架构数据访问"""

    @staticmethod
    def get_tree(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        org_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取组织架构树（按权限过滤）

        Args:
            user_id: 当前用户 ID
            data_scope: 权限范围（all / region / self）
            wework_account_id: 当前企微账户 ID（可能为 None）
            org_id: 可选，从指定节点开始展开（不传则从根节点开始）

        Returns:
            组织树列表，每个节点包含 children 字段
        """
        with session_scope() as session:
            # 第一步：根据权限获取可见的组织 ID 列表（复用同一连接）
            visible_org_ids = OrganizationDAO._get_visible_org_ids(
                user_id, data_scope, wework_account_id, org_id, session=session
            )

            if not visible_org_ids:
                return []

            # 第二步：查询这些组织的详细信息
            rows = (
                session.query(SysOrganization)
                .filter(SysOrganization.org_id.in_(visible_org_ids))
                .order_by(SysOrganization.sort_order.asc(), SysOrganization.org_id.asc())
                .all()
            )

            # 转成 dict 方便查找
            org_map = {row.org_id: {**_org_dict(row), "children": []} for row in rows}

            # 构建树
            roots = []
            for org in org_map.values():
                parent_id = org["parent_org_id"]
                if parent_id is None or parent_id not in org_map:
                    roots.append(org)
                else:
                    org_map[parent_id]["children"].append(org)

            return roots

    @staticmethod
    def _get_visible_org_ids(
        user_id: str,
        data_scope: str,
        wework_account_id: Optional[str],
        org_id: Optional[str] = None,
        session=None,
    ) -> List[str]:
        """
        根据权限获取用户可见的组织 ID 列表（内部方法）
        支持外部传入 session 以复用，不传则自行管理会话生命周期。
        """
        if session is None:
            with session_scope() as s:
                return OrganizationDAO._get_visible_org_ids(
                    user_id, data_scope, wework_account_id, org_id, session=s
                )

        if data_scope == "all":
            # 超级管理员：返回全部组织
            if org_id:
                # 如果指定了起始节点，返回该节点及其所有子节点
                return OrganizationDAO._get_subtree_ids(session, org_id)
            rows = session.query(SysOrganization.org_id).all()
            return [r.org_id for r in rows]

        if data_scope == "region":
            # 区域主管：返回本区域（含子组织）全部组织
            if not wework_account_id:
                return []

            # 先查该企微账户对应的区域 org_id
            region_row = (
                session.query(SysOrganization)
                .filter(
                    SysOrganization.wework_account_id == wework_account_id,
                    SysOrganization.org_type == "区域",
                )
                .first()
            )
            if not region_row:
                return []

            region_org_id = region_row.org_id

            if org_id:
                # 如果指定了起始节点，只返回该节点下且在本区域范围内的组织
                subtree = OrganizationDAO._get_subtree_ids(session, org_id)
                # 过滤：只保留本区域下的
                region_subtree = OrganizationDAO._get_subtree_ids(session, region_org_id)
                return [oid for oid in subtree if oid in region_subtree]
            return OrganizationDAO._get_subtree_ids(session, region_org_id)

        if data_scope == "self":
            # 普通顾问：只返回本人所属的组织
            if not wework_account_id:
                return []

            # 查询当前用户的 org_id
            emp_row = (
                session.query(SysEmployee)
                .filter(SysEmployee.user_id == user_id)
                .first()
            )
            if not emp_row or not emp_row.org_id:
                return []

            user_org_id = emp_row.org_id

            if org_id:
                # 如果指定了节点，检查是否在用户所属组织路径下
                if OrganizationDAO._is_descendant_of(session, org_id, user_org_id):
                    return OrganizationDAO._get_subtree_ids(session, org_id)
                return []
            # 返回用户所属组织及其子组织
            return OrganizationDAO._get_subtree_ids(session, user_org_id)

        return []

    @staticmethod
    def _get_subtree_ids(session, root_org_id: str) -> List[str]:
        """
        获取指定组织节点下的所有子节点 ID（含自身）
        使用递归 CTE（MySQL 8.0+ 支持）
        """
        subtree = (
            select(SysOrganization.org_id, SysOrganization.parent_org_id)
            .where(SysOrganization.org_id == root_org_id)
            .cte(recursive=True, name="org_tree")
        )
        subtree = subtree.union_all(
            select(SysOrganization.org_id, SysOrganization.parent_org_id).join(
                subtree, SysOrganization.parent_org_id == subtree.c.org_id
            )
        )
        rows = session.execute(select(subtree.c.org_id)).all()
        return [r[0] for r in rows]

    @staticmethod
    def _is_descendant_of(session, node_id: str, ancestor_id: str) -> bool:
        """检查 node_id 是否是 ancestor_id 的子孙节点（含自身）"""
        descendants = OrganizationDAO._get_subtree_ids(session, ancestor_id)
        return node_id in descendants

    @staticmethod
    def get_by_org_id(org_id: str) -> Optional[Dict]:
        """按 org_id 查询单个组织"""
        with session_scope() as session:
            r = (
                session.query(SysOrganization)
                .filter(SysOrganization.org_id == org_id)
                .first()
            )
            return _org_dict(r) if r else None

    @staticmethod
    def get_children(org_id: str) -> List[Dict]:
        """获取某个组织的直接子组织列表"""
        with session_scope() as session:
            rows = (
                session.query(SysOrganization)
                .filter(SysOrganization.parent_org_id == org_id)
                .order_by(SysOrganization.sort_order.asc(), SysOrganization.org_id.asc())
                .all()
            )
            return [_org_dict(r) for r in rows]

    @staticmethod
    def get_by_account(account_id: str) -> List[Dict]:
        """按企微账户查询所有组织"""
        with session_scope() as session:
            rows = (
                session.query(SysOrganization)
                .filter(SysOrganization.wework_account_id == account_id)
                .order_by(SysOrganization.sort_order.asc(), SysOrganization.org_id.asc())
                .all()
            )
            return [_org_dict(r) for r in rows]

    @staticmethod
    def create(
        org_id: str,
        org_name: str,
        org_type: str,
        wework_account_id: str,
        parent_org_id: Optional[str] = None,
        sort_order: int = 0,
    ) -> bool:
        """新增组织节点"""
        with session_scope(commit=True) as session:
            session.add(
                SysOrganization(
                    org_id=org_id,
                    org_name=org_name,
                    parent_org_id=parent_org_id,
                    org_type=org_type,
                    wework_account_id=wework_account_id,
                    sort_order=sort_order,
                )
            )
            return True

    @staticmethod
    def update(org_id: str, **kwargs) -> bool:
        """更新组织节点（只更新传入的字段）"""
        allowed_fields = {"org_name", "parent_org_id", "sort_order"}
        with session_scope(commit=True) as session:
            row = (
                session.query(SysOrganization)
                .filter(SysOrganization.org_id == org_id)
                .first()
            )
            if not row:
                return False
            updated = False
            for key, value in kwargs.items():
                if key in allowed_fields and value is not None:
                    setattr(row, key, value)
                    updated = True
            return updated

    @staticmethod
    def delete(org_id: str) -> bool:
        """删除组织节点（如果有子节点则不允许删除）"""
        # 先检查是否有子节点
        children = OrganizationDAO.get_children(org_id)
        if children:
            raise ValueError(f"组织 {org_id} 下存在子组织，请先删除子组织")

        with session_scope(commit=True) as session:
            result = session.execute(
                delete(SysOrganization).where(SysOrganization.org_id == org_id)
            )
            return result.rowcount > 0

    @staticmethod
    def get_path(org_id: str) -> List[str]:
        """
        获取从根节点到指定节点的路径（组织 ID 列表）
        用于面包屑导航或权限继承判断
        """
        with session_scope() as session:
            org_path = (
                select(
                    SysOrganization.org_id,
                    SysOrganization.parent_org_id,
                    literal(1).label("depth"),
                )
                .where(SysOrganization.org_id == org_id)
                .cte(recursive=True, name="org_path")
            )
            parent_alias = org_path.alias("p")
            org_alias = SysOrganization.__table__.alias("o")
            org_path = org_path.union_all(
                select(
                    org_alias.c.org_id,
                    org_alias.c.parent_org_id,
                    (parent_alias.c.depth + 1).label("depth"),
                ).join(parent_alias, org_alias.c.org_id == parent_alias.c.parent_org_id)
            )
            rows = session.execute(
                select(org_path.c.org_id).order_by(org_path.c.depth.desc())
            ).all()
            return [r[0] for r in rows]
