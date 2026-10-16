from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped,mapped_column
from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base
class KnowledgeCurationProposal(V1Base):
    __tablename__='knowledge_curation_proposal'
    __table_args__=(Index('ix_v1_curation_project_status','project_id','status'),Index('ix_v1_curation_source','source_kind','source_ref'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    project_id:Mapped[str|None]=mapped_column(ForeignKey('project.id',ondelete='SET NULL'),nullable=True,index=True)
    source_kind:Mapped[str]=mapped_column(String(40),nullable=False)
    source_ref:Mapped[str]=mapped_column(String(80),nullable=False,default='')
    status:Mapped[str]=mapped_column(String(24),nullable=False,default='draft',index=True)
    proposed_action:Mapped[str]=mapped_column(String(40),nullable=False,default='defer')
    title:Mapped[str]=mapped_column(String(240),nullable=False)
    payload_json:Mapped[str]=mapped_column(Text,nullable=False,default='{}')
    reviewer:Mapped[str]=mapped_column(String(120),nullable=False,default='')
    review_reason:Mapped[str]=mapped_column(Text,nullable=False,default='')
    expected_state_version:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    exported_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,onupdate=utc_now,nullable=False)
