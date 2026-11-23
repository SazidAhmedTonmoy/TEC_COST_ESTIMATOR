import {useEffect,useId,useLayoutEffect,useMemo,useRef,useState,type CSSProperties,type ReactNode} from 'react';
import {createPortal} from 'react-dom';

export type CalendarDetail={label:string;value:string};
export type MonthCalendarEvent={
  id:string;date:string;title:string;kind:string;accent?:string;documentsAvailable?:boolean;details:CalendarDetail[];
  note?:string;onOpen:()=>void;actionLabel?:string;
};
export type MonthCell={date:string;inMonth:boolean;weekend:boolean};

/** Monday-first calendar dates use UTC arithmetic so DST never skips a cell. */
export function monthCalendarCells(month:string):MonthCell[]{
  if(!/^\d{4}-(0[1-9]|1[0-2])$/.test(month))return [];
  const [year,number]=month.split('-').map(Number);
  const first=new Date(Date.UTC(year,number-1,1));
  const offset=(first.getUTCDay()+6)%7;
  const count=new Date(Date.UTC(year,number,0)).getUTCDate();
  return Array.from({length:Math.ceil((offset+count)/7)*7},(_,index)=>{
    const date=new Date(Date.UTC(year,number-1,index-offset+1)).toISOString().slice(0,10);
    return {date,inMonth:date.startsWith(month),weekend:index%7>4};
  });
}

const fullDate=(date:string)=>new Date(date+'T12:00:00Z').toLocaleDateString('en-AU',{timeZone:'UTC',weekday:'long',day:'numeric',month:'long',year:'numeric'});

function eventInk(accent:string){
  const hex=accent.replace('#','');
  if(!/^[\da-f]{6}$/i.test(hex))return '#fff';
  const rgb=[0,2,4].map(offset=>parseInt(hex.slice(offset,offset+2),16)/255).map(value=>value<=.04045?value/12.92:((value+.055)/1.055)**2.4);
  return rgb[0]*.2126+rgb[1]*.7152+rgb[2]*.0722>.179?'#000':'#fff';
}

export function CalendarMonthToolbar({month,onPrevious,onNext,onToday,onMonthChange,monthLabel='Choose calendar month',children}:{
  month:string;onPrevious:()=>void;onNext:()=>void;onToday:()=>void;onMonthChange:(month:string)=>void;monthLabel?:string;children?:ReactNode;
}){
  return <div className="flow-calendar-toolbar">
    <div className="flow-calendar-nav" role="group" aria-label="Calendar navigation">
      <button type="button" onClick={onToday}>Today</button>
      <button type="button" aria-label="Previous month" onClick={onPrevious}>Back</button>
      <button type="button" aria-label="Next month" onClick={onNext}>Next</button>
    </div>
    <h2>{new Date(month+'-01T12:00:00Z').toLocaleDateString('en-AU',{timeZone:'UTC',month:'long',year:'numeric'})}</h2>
    <div className="flow-calendar-tools"><input type="month" aria-label={monthLabel} value={month} onChange={event=>{if(event.target.value)onMonthChange(event.target.value)}}/>{children}</div>
  </div>;
}

/** The preview is portalled so scrollable calendars never cut off its contents. */
export function CalendarEventButton({event}:{event:MonthCalendarEvent}){
  const id=useId(),anchor=useRef<HTMLButtonElement>(null),preview=useRef<HTMLDivElement>(null);
  const closeTimer=useRef<ReturnType<typeof setTimeout>|null>(null);
  const [open,setOpen]=useState(false),[position,setPosition]=useState({left:0,top:0,ready:false});
  function cancelClose(){if(closeTimer.current!==null){clearTimeout(closeTimer.current);closeTimer.current=null}}
  function show(){cancelClose();setOpen(true)}
  function hide(){cancelClose();setOpen(false)}
  function leave(){cancelClose();closeTimer.current=setTimeout(()=>setOpen(false),160)}
  useEffect(()=>()=>cancelClose(),[]);
  useLayoutEffect(()=>{
    if(!open)return;
    function place(){
      if(!anchor.current||!preview.current)return;
      const target=anchor.current.getBoundingClientRect(),card=preview.current.getBoundingClientRect();
      const gap=9,pad=12,width=document.documentElement.clientWidth,height=window.innerHeight;
      let left=target.left,top=target.bottom+gap;
      if(top+card.height>height-pad)top=target.top-card.height-gap;
      left=Math.max(pad,Math.min(left,width-card.width-pad));
      top=Math.max(pad,Math.min(top,height-card.height-pad));
      setPosition({left,top,ready:true});
    }
    function dismiss(event:KeyboardEvent){if(event.key==='Escape'){event.preventDefault();hide()}}
    function closeOutside(event:PointerEvent){if(!anchor.current?.contains(event.target as Node)&&!preview.current?.contains(event.target as Node))hide()}
    place();
    window.addEventListener('resize',place);
    window.addEventListener('scroll',place,true);
    document.addEventListener('keydown',dismiss);
    document.addEventListener('pointerdown',closeOutside);
    return()=>{window.removeEventListener('resize',place);window.removeEventListener('scroll',place,true);document.removeEventListener('keydown',dismiss);document.removeEventListener('pointerdown',closeOutside)};
  },[open]);
  const accent=event.accent||'#0f6cbd';
  const documentsMissing=event.documentsAvailable===false;
  const color={'--flow-event-accent':accent,'--flow-event-ink':eventInk(accent)} as CSSProperties;
  return <>
    <button ref={anchor} type="button" className={"flow-calendar-event"+(documentsMissing?" is-documents-pending":"")} style={color}
      aria-label={`${event.kind}: ${event.title}.${documentsMissing?" Documents not available.":""} ${event.actionLabel||'Open details'}`}
      aria-describedby={open?id:undefined}
      onPointerEnter={e=>{if(e.pointerType!=='touch')show()}} onPointerLeave={leave}
      onFocus={show} onBlur={hide} onClick={()=>{hide();event.onOpen()}}>
      <span className="flow-event-title">{event.title}</span>
    </button>
    {open&&createPortal(<div ref={preview} id={id} role="tooltip" className="flow-calendar-preview"
      style={{...color,left:position.left,top:position.top,visibility:position.ready?'visible':'hidden'}}
      onPointerEnter={cancelClose} onPointerLeave={leave}>
      <div className="flow-preview-header"><div className="flow-preview-kind"><i aria-hidden="true"/>{event.kind}</div>
        <strong className="flow-preview-title">{event.title}</strong></div>
      <div className="flow-preview-body"><dl>{event.details.filter(item=>item.value).map((item,index)=><div key={item.label+index}><dt>{item.label}</dt><dd>{item.value}</dd></div>)}</dl>
        {event.note&&<p className="flow-preview-note">{event.note}</p>}
        <span className="flow-preview-hint">{event.actionLabel||'Open details'} · press Enter or click the event</span></div>
    </div>,document.body)}
  </>;
}

export function MonthCalendar({month,today,selectedDay,events,onSelectDate,label}:{
  month:string;today:string;selectedDay:string;events:MonthCalendarEvent[];onSelectDate:(date:string)=>void;label:string;
}){
  const cells=useMemo(()=>monthCalendarCells(month),[month]);
  const byDate=useMemo(()=>{
    const result=new Map<string,MonthCalendarEvent[]>();
    for(const event of events){const values=result.get(event.date)||[];values.push(event);result.set(event.date,values)}
    return result;
  },[events]);
  return <section className="flow-month-calendar" aria-label={label}>
    <div className="flow-month-scroll">
      <div className="flow-month-weekdays">{['Mon','Tue','Wed','Thu','Fri','Sat','Sun'].map((day,index)=><span key={day} className={index>4?'is-weekend':''}><b>{day}</b>{index>4&&<small>Off day</small>}</span>)}</div>
      <div className="flow-month-grid">{cells.map(cell=>{
        const entries=cell.inMonth?byDate.get(cell.date)||[]:[];
        return <div key={cell.date} className={'flow-month-day'+(!cell.inMonth?' is-outside':'')+(cell.weekend?' is-weekend':'')+(cell.date===today?' is-today':'')+(cell.date===selectedDay?' is-selected':'')}
          onClick={event=>{if(cell.inMonth&&!(event.target as HTMLElement).closest('button,a'))onSelectDate(cell.date)}}>
          <div className="flow-month-day-heading"><button type="button" className="flow-month-date" disabled={!cell.inMonth}
            aria-label={(cell.date===today?'Today, ':'')+fullDate(cell.date)+(cell.weekend?', Off day':'')} aria-current={cell.date===today?'date':undefined}
            aria-pressed={cell.inMonth?cell.date===selectedDay:undefined} onClick={()=>onSelectDate(cell.date)}>{cell.date.slice(-2)}</button>
            {cell.date===today&&<span className="flow-month-today-label">Today</span>}
          </div>
          <div className="flow-month-events">{entries.slice(0,2).map(event=><CalendarEventButton key={event.id} event={event}/>)}</div>
          {entries.length>2&&<button type="button" className="flow-month-more" onClick={()=>onSelectDate(cell.date)} aria-label={`Show all ${entries.length} events on ${fullDate(cell.date)}`}>+{entries.length-2} more</button>}
        </div>;
      })}</div>
    </div>
    <div className="flow-month-footer"><span>Hover or focus on a project for details</span><span>Select a date to see its agenda below</span></div>
  </section>;
}
