from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped,mapped_column
from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base
class RecruitmentPlan(V1Base):
    __tablename__='recruitment_plan'
    __table_args__=(UniqueConstraint('project_id',name='uq_v1_recruitment_plan_project'),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    project_id:Mapped[str]=mapped_column(ForeignKey('project.id',ondelete='CASCADE'),nullable=False,unique=True,index=True)
    target_hires:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    target_date:Mapped[str]=mapped_column(String(32),nullable=False,default='')
    owner:Mapped[str]=mapped_column(String(120),nullable=False,default='')
    source_channels_json:Mapped[str]=mapped_column(Text,nullable=False,default='[]')
    notes:Mapped[str]=mapped_column(Text,nullable=False,default='')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,onupdate=utc_now,nullable=False)
