from __future__ import annotations
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from srw.kernel.clock import utc_now
from srw.kernel.ids import new_id
from srw.runtime.db.base import V1Base

class DecisionAction(V1Base):
    __tablename__='decision_action'
    __table_args__=(Index('ix_v1_decision_action_project_status','project_id','status'),Index('ix_v1_decision_action_candidate_status','candidate_id','status'),Index('ix_v1_decision_action_content_hash','content_hash'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    project_id:Mapped[str]=mapped_column(ForeignKey('project.id',ondelete='CASCADE'),nullable=False,index=True)
    candidate_id:Mapped[str]=mapped_column(ForeignKey('candidate.id',ondelete='CASCADE'),nullable=False,index=True)
    action_type:Mapped[str]=mapped_column(String(40),nullable=False)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default='proposed',index=True)
    priority:Mapped[int]=mapped_column(Integer,nullable=False,default=50)
    reason_code:Mapped[str]=mapped_column(String(80),nullable=False)
    reason_text:Mapped[str]=mapped_column(Text,nullable=False)
    criterion_key:Mapped[str]=mapped_column(String(128),nullable=False,default='')
    decision_context_hash:Mapped[str]=mapped_column(String(64),nullable=False,index=True)
    content_hash:Mapped[str]=mapped_column(String(64),nullable=False,index=True)
    accepted_by:Mapped[str]=mapped_column(String(120),nullable=False,default='')
    accepted_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    completed_by:Mapped[str]=mapped_column(String(120),nullable=False,default='')
    completed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    outcome_json:Mapped[str]=mapped_column(Text,nullable=False,default='{}')
    expected_state_version:Mapped[int]=mapped_column(Integer,nullable=False,default=1)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,onupdate=utc_now,nullable=False)

class KnowledgeFeedbackDraft(V1Base):
    __tablename__='knowledge_feedback_draft'
    __table_args__=(Index('ix_v1_knowledge_feedback_project_status','project_id','status'),Index('ix_v1_knowledge_feedback_action','decision_action_id'),Index('ix_v1_knowledge_feedback_hash','content_hash'))
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=new_id)
    project_id:Mapped[str]=mapped_column(ForeignKey('project.id',ondelete='CASCADE'),nullable=False,index=True)
    candidate_id:Mapped[str]=mapped_column(ForeignKey('candidate.id',ondelete='CASCADE'),nullable=False,index=True)
    decision_action_id:Mapped[str]=mapped_column(ForeignKey('decision_action.id',ondelete='CASCADE'),nullable=False,index=True)
    status:Mapped[str]=mapped_column(String(24),nullable=False,default='draft',index=True)
    feedback_type:Mapped[str]=mapped_column(String(40),nullable=False)
    title:Mapped[str]=mapped_column(String(240),nullable=False)
    summary:Mapped[str]=mapped_column(Text,nullable=False)
    evidence_refs_json:Mapped[str]=mapped_column(Text,nullable=False,default='[]')
    outcome_snapshot_json:Mapped[str]=mapped_column(Text,nullable=False,default='{}')
    decision_context_hash:Mapped[str]=mapped_column(String(64),nullable=False)
    content_hash:Mapped[str]=mapped_column(String(64),nullable=False,index=True)
    reviewed_by:Mapped[str]=mapped_column(String(120),nullable=False,default='')
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True),nullable=True)
    review_reason:Mapped[str]=mapped_column(Text,nullable=False,default='')
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=utc_now,nullable=False)
