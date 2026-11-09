"""Self-contained editable CadQuery source. Run: python model.py parameters.json output_dir"""
import json, sys, itertools
from pathlib import Path
from xml.etree import ElementTree as ET
import cadquery as cq

DEFAULTS=dict(screen_width=120,screen_height=70,speaker_width=80,height=140,depth=55,wall=3)

def validate(p):
    if set(p)!=set(DEFAULTS):raise ValueError('参数字段不完整或包含未知参数')
    limits={'screen_width':(40,300),'screen_height':(30,200),'speaker_width':(30,200),'height':(100,300),'depth':(25,150),'wall':(2,6)}
    for key,(lo,hi) in limits.items():
        if not isinstance(p[key],(float,int)) or not lo<=p[key]<=hi:raise ValueError(f'{key} 必须位于 {lo}–{hi} mm')
    if p['screen_height']+44>p['height']:raise ValueError('屏幕与上下灯带/边框冲突：外壳高度至少为屏幕高度 + 44 mm')
    return p

def build(p):
    validate(p)
    sw,sh,sp,h,d,t=[p[k] for k in ('screen_width','screen_height','speaker_width','height','depth','wall')]
    w=sw+sp+48
    sx=-w/2+16+sw/2
    px=w/2-16-sp/2
    shell=cq.Workplane('XY').box(w,h,d).cut(cq.Workplane('XY').box(w-2*t,h-2*t,d).translate((0,0,t)))
    front=cq.Workplane('XY').box(w,h,t).translate((0,0,d/2-t/2))
    front=front.cut(cq.Workplane('XY').box(sw+1,sh+1,t*3).translate((sx,0,d/2)))
    front=front.cut(cq.Workplane('XY').box(sp+1,sh+1,t*3).translate((px,0,d/2)))
    for y in (-h/2+14,h/2-14):front=front.cut(cq.Workplane('XY').box(w-40,7,t*3).translate((0,y,d/2)))
    shell=shell.union(front)
    for x,y in itertools.product((-w/2+9,w/2-9),(-h/2+9,h/2-9)):
        shell=shell.cut(cq.Workplane('XY').center(x,y).circle(2.2).extrude(d*2,both=True))
    parts={'enclosure':shell,
           'display_envelope':cq.Workplane('XY').box(sw,sh,2).translate((sx,0,d/2-1)),
           'speaker_envelope':cq.Workplane('XY').box(sp,sh,10).translate((px,0,d/2-5))}
    for i,y in enumerate((-h/2+14,h/2-14)):
        parts[f'strobe_{i+1}']=cq.Workplane('XY').box(w-41,6,2).translate((0,y,d/2-1))
    for name,obj in parts.items():
        if not obj.val().isValid():raise ValueError('几何无效：'+name)
    intersections=[]
    for (a,pa),(b,pb) in itertools.combinations(parts.items(),2):
        v=pa.val().intersect(pb.val()).Volume()
        if v>1e-5:intersections.append({'parts':[a,b],'volume':v})
    if intersections:raise ValueError('零件干涉：'+str(intersections))
    compound=cq.Compound.makeCompound([x.val() for x in parts.values()])
    return compound,parts,{'width':w,'height':h,'depth':d,'interferences':intersections,'solids':len(compound.Solids())}

def generate(p,out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    model,parts,checks=build(p)
    cq.exporters.export(model,str(out/'model.step'))
    reopened=cq.importers.importStep(str(out/'model.step')).val()
    if not reopened.isValid() or abs(reopened.Volume()-model.Volume())>max(0.01,model.Volume()*1e-6):raise ValueError('STEP 重新打开校验失败')
    bb=reopened.BoundingBox()
    checks.update(step_reopened=True,volume_mm3=reopened.Volume(),bbox_mm=[bb.xlen,bb.ylen,bb.zlen],engine='CadQuery '+cq.__version__,units='mm',status='概念/初步工程草案，未完成可制造性评审')
    for name,direction in [('front',(0,0,1)),('top',(0,1,0)),('side',(1,0,0)),('isometric',(1,-1,1))]:
        cq.exporters.export(model,str(out/(name+'.svg')),opt={'width':480,'height':260,'projectionDir':direction,'showAxes':False,'showHidden':False,'strokeWidth':0.6,'strokeColor':(42,61,77)})
    # All view geometry is OpenCascade hidden-line projection of the exported solid.
    ns='http://www.w3.org/2000/svg'
    ET.register_namespace('',ns)
    drawing=ET.Element('{'+ns+'}svg',{'width':'1040','height':'720','viewBox':'0 0 1040 720'})
    ET.SubElement(drawing,'{'+ns+'}rect',{'width':'1040','height':'720','fill':'#fff'})
    for i,name in enumerate(('front','top','side','isometric')):
        view=ET.parse(out/(name+'.svg')).getroot();view.set('x',str(20+(i%2)*510));view.set('y',str(60+(i//2)*300));drawing.append(view)
        text=ET.SubElement(drawing,'{'+ns+'}text',{'x':str(45+(i%2)*510),'y':str(85+(i//2)*300),'font-size':'15','fill':'#243a4a'})
        text.text={'front':f'FRONT — W {checks["width"]:g} × H {p["height"]:g} mm','top':f'TOP — W {checks["width"]:g} × D {p["depth"]:g} mm','side':f'SIDE — D {p["depth"]:g} × H {p["height"]:g} mm','isometric':'ISOMETRIC — 5 solids / concept'}[name]
    # Dimension lines match the front projection bounds, with units explicitly stated.
    front=ET.parse(out/'front.svg').getroot()
    g=next(el for el in front.iter() if el.tag.endswith('g') and 'scale' in el.get('transform',''))
    import re
    scale=float(re.search(r'scale\(([-\d.eE]+)',g.get('transform')).group(1))
    transform=g.get('transform')
    shift=re.search(r'translate\(([-\d.eE]+)[,\s]+([-\d.eE]+)\)',transform)
    # SVG exporter uses scale then translate; derive x projection limits from actual bounding box.
    tx=float(shift.group(1)) if shift else 0
    x1=20+scale*(tx-bb.xlen/2);x2=20+scale*(tx+bb.xlen/2)
    for a,b,c,d in [(x1,320,x2,320),(x1,313,x1,327),(x2,313,x2,327)]:
        ET.SubElement(drawing,'{'+ns+'}line',{'x1':str(a),'y1':str(b),'x2':str(c),'y2':str(d),'stroke':'#177d75'})
    t=ET.SubElement(drawing,'{'+ns+'}text',{'x':str((x1+x2)/2),'y':'315','text-anchor':'middle','fill':'#177d75','font-size':'13'});t.text=f'{checks["width"]:g} mm'
    for y,text in [(32,'PRODUCT TERMINAL / STRUCTURAL CONCEPT'),(680,f'Screen {p["screen_width"]:g} × {p["screen_height"]:g} | Speaker area {p["speaker_width"]:g} | Wall {p["wall"]:g} mm | Mount holes 4 × Ø4.4'),(704,'NOT FOR PRODUCTION — component envelopes only; tolerances, acoustics, thermals and electrical design require review.')]:
        t=ET.SubElement(drawing,'{'+ns+'}text',{'x':'30','y':str(y),'font-size':'13','fill':'#243a4a'});t.text=text
    ET.ElementTree(drawing).write(out/'drawing.svg',encoding='unicode',xml_declaration=True)
    (out/'parameters.json').write_text(json.dumps(p,indent=2))
    (out/'checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2))
    (out/'model.py').write_text(Path(__file__).read_text())
    return checks

if __name__=='__main__':
    print(json.dumps(generate(json.loads(Path(sys.argv[1]).read_text()),sys.argv[2]),ensure_ascii=False,indent=2))
