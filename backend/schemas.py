from pydantic import BaseModel, Field, ConfigDict, field_validator
from typing import Literal
class Strict(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
class Login(Strict):
    name:str=Field(min_length=2,max_length=80)
    password:str=Field(min_length=1,max_length=200)
class Project(Strict):
    name:str=Field(min_length=2,max_length=120)
    direction:str=Field(min_length=3,max_length=2000)
    constraints:str=Field(default='',max_length=4000)
class Profile(Strict):
    industry:str=''
    scenario:str=''
    region:str=''
    scale:str=''
    buyer:str=''
    needs:str=''
    budget:str=''
    exclusions:str=''
class Competitor(Strict):
    brand:str=Field(min_length=1,max_length=100)
    model:str=Field(min_length=1,max_length=200)
    url:str=Field(default='',max_length=2000)
    summary:str=Field(default='',max_length=12000)
    provenance:Literal['manual','demo']='manual'
class Fact(Strict):
    text:str=Field(min_length=1,max_length=2000)
    quote:str=Field(default='',max_length=2000)
    source_id:str=''
    status:Literal['pending','verified']='pending'
class Baseline(Strict):
    competitor_id:str
    reason:str=Field(min_length=2,max_length=2000)
    facts:list[Fact]=Field(default_factory=list,max_length=50)
    unknowns:list[str]=Field(default_factory=lambda:['内部结构与未公开尺寸待核实'])
class Feedback(Strict):
    quote:str=Field(min_length=3,max_length=8000)
    source:str=Field(min_length=1,max_length=500)
    customer_key:str=''
    scenario:str=''
    provenance:Literal['manual','demo']='manual'
class Allocation(Strict):
    software:str=Field(min_length=2,max_length=4000)
    hardware:str=Field(min_length=2,max_length=4000)
    interface:str=Field(min_length=2,max_length=4000)
    acceptance:str=Field(min_length=2,max_length=4000)
class Need(Strict):
    title:str=Field(min_length=2,max_length=300)
    description:str=Field(min_length=2,max_length=4000)
    feedback_ids:list[str]=Field(min_length=1,max_length=100)
    allocation:Allocation
    status:Literal['pending','confirmed','rejected']='pending'
class Feature(Strict):
    name:str
    need_ids:list[str]=Field(min_length=1)
    relationship:Literal['保留','修改','删除','新增']
    premier_behavior:str
    our_behavior:str
    rationale:str
    risks:str
class Proposal(Strict):
    name:str
    features:list[Feature]=Field(min_length=1,max_length=30)
class Proposals(Strict):
    proposals:list[Proposal]=Field(min_length=2,max_length=4)
class NeedResult(Strict):
    needs:list[Need]=Field(min_length=1,max_length=30)
class Generation(Strict):
    mode:Literal['live','demo']='live'
    query:str=Field(default='',max_length=500)
class Match(Strict):
    event_id:str=Field(min_length=3,max_length=100)
    project_id:str
    profile_version:str
    source_system:str=Field(min_length=1,max_length=100)
    external_customer_id:str=Field(min_length=1,max_length=100)
    customer_name:str=Field(min_length=1,max_length=200)
    industry:str=''
    region:str=''
    owner:str=''
    reasons:list[str]=Field(default_factory=list,max_length=20)
    hard_conditions:list[str]=Field(default_factory=list,max_length=20)
    preferences:list[str]=Field(default_factory=list,max_length=20)
    crm_url:str=''
    updated_at:str
    action:Literal['upsert','withdraw']='upsert'
    @field_validator('updated_at')
    @classmethod
    def date(cls,v):
        from datetime import datetime
        d=datetime.fromisoformat(v.replace('Z','+00:00'))
        if not d.tzinfo:raise ValueError('时间须包含时区')
        return d.isoformat()
class CADParams(Strict):
    screen_width:float=Field(default=120,ge=40,le=300)
    screen_height:float=Field(default=70,ge=30,le=200)
    speaker_width:float=Field(default=80,ge=30,le=200)
    height:float=Field(default=140,ge=100,le=300)
    depth:float=Field(default=55,ge=25,le=150)
    wall:float=Field(default=3,ge=2,le=6)
class CADRequest(Strict):
    parameters:CADParams
    confirmed:bool=False
    note:str='参数为项目概念值，不来自竞品内部尺寸'
