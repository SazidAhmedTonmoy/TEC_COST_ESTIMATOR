import type {Opportunity,OpportunityRegion,OpportunityStatus} from './opportunity-types';

const DAY_MS=86_400_000;
const defaultTimezones:Record<string,string>={NSW:'Australia/Sydney',VIC:'Australia/Melbourne'};
const dateFormatters=new Map<string,Intl.DateTimeFormat>();

function dateFormatter(timezone:string) {
  let formatter=dateFormatters.get(timezone);
  if(!formatter){
    formatter=new Intl.DateTimeFormat('en-AU',{timeZone:timezone,calendar:'gregory',numberingSystem:'latn',year:'numeric',month:'2-digit',day:'2-digit'});
    dateFormatters.set(timezone,formatter);
  }
  return formatter;
}

/** Use the same regional calendar as the server, independent of the viewer's device. */
export function opportunityTimezone(region:string,regions:OpportunityRegion[]=[]) {
  const code=(region||'').trim().toUpperCase();
  const configured=regions.find(item=>item.code.toUpperCase()===code)?.timezone;
  if(configured){try{dateFormatter(configured);return configured}catch{/* Fall back if an older region has invalid timezone metadata. */}}
  return defaultTimezones[code]||'Australia/Sydney';
}

function localDay(now:number,timezone:string) {
  const parts=dateFormatter(timezone).formatToParts(now);
  const part=(kind:string)=>Number(parts.find(item=>item.type===kind)!.value);
  const date=new Date(0);
  date.setUTCFullYear(part('year'),part('month')-1,part('day'));
  date.setUTCHours(0,0,0,0);
  return date.getTime()/DAY_MS;
}

function deadlineDay(value:string) {
  if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null;
  const instant=Date.parse(value+'T00:00:00Z');
  if(!Number.isFinite(instant)||new Date(instant).toISOString().slice(0,10)!==value)return null;
  return instant/DAY_MS;
}

export type OpportunityDeadline={days:number|null;label:string;tone:'urgent'|'warning'|'safe'|'neutral'|'none';timezone:string};

export function opportunityLocalDate(region:string,regions:OpportunityRegion[]=[],now=Date.now()) {
  return new Date(localDay(now,opportunityTimezone(region,regions))*DAY_MS).toISOString().slice(0,10);
}

export function opportunityDeadline(
  item:{due?:string;region:string;status?:OpportunityStatus},
  regions:OpportunityRegion[]=[],
  now=Date.now(),
):OpportunityDeadline {
  const timezone=opportunityTimezone(item.region,regions);
  const decided=item.status==='approved'||item.status==='rejected'||item.status==='expired';
  if(!item.due)return {days:null,label:'No deadline',tone:decided?'neutral':'none',timezone};
  const due=deadlineDay(item.due);
  if(due===null)return {days:null,label:'Deadline unavailable',tone:decided?'neutral':'none',timezone};
  // Calendar ordinals avoid rounding errors on 23-hour and 25-hour DST days.
  const days=due-localDay(now,timezone);
  if(days<0){
    const age=-days;
    const prefix=item.status==='expired'?'Expired':'Deadline passed';
    return {days,label:`${prefix} ${age} day${age===1?'':'s'} ago`,tone:'neutral',timezone};
  }
  return {days,label:days===0?'Due today':days===1?'Due tomorrow':`${days} days left`,tone:decided?'neutral':days<=3?'urgent':days<=7?'warning':'safe',timezone};
}

export function isOpportunityQuoted(item:Pick<Opportunity,'quoteStatus'|'submissionIds'>) {
  return item.quoteStatus==='quoted'||!!item.submissionIds?.length;
}

/** An approved, unlinked opportunity can be quoted even after its deadline.
 * The deadline controls urgency, not the recorded approval decision.
 * Linked tenders are managed in Chase-up rather than converted twice. */
export function canQuoteOpportunity(item:Opportunity,_regions:OpportunityRegion[]=[],_now=Date.now()) {
  return !item.deletedAt&&item.status==='approved'&&!isOpportunityQuoted(item)&&!item.linkedAt&&
    !!(item.permissions.quote??item.permissions.approve);
}

/** Reject is only offered during Awaiting approval.
 * Approved opportunities use Not quoted while the quote workflow is active;
 * Expired and decided opportunities remain read-only for this decision. */
export function canRejectOpportunity(item:Opportunity,_regions:OpportunityRegion[]=[],_now=Date.now()) {
  if(item.deletedAt||!item.permissions.approve||isOpportunityQuoted(item))return false;
  return item.status==='pending';
}

/** Next local midnight across the visible regions; no fixed 24-hour assumption. */
export function nextOpportunityDayChange(timezones:string[],now=Date.now()) {
  let next=Infinity;
  for(const timezone of new Set(timezones.length?timezones:['Australia/Sydney'])){
    const today=localDay(now,timezone);
    let low=Math.floor(now),high=low+2*DAY_MS;
    // Only runs when scheduling a daily refresh, not for each opportunity card.
    while(high-low>1){
      const middle=Math.floor((low+high)/2);
      if(localDay(middle,timezone)===today)low=middle;else high=middle;
    }
    next=Math.min(next,high);
  }
  return next;
}

/** Google Maps directions from the opportunity's nominated or regional origin. */
export function opportunityRouteUrl(
  item:Pick<Opportunity,'location'|'region'|'distanceOrigin'>,
  regions:OpportunityRegion[]=[],
) {
  const destination=(item.location||'').trim();
  if(!destination)return '';
  const origin=(item.distanceOrigin||regions.find(r=>r.code===item.region)?.origin||'').trim();
  const query=new URLSearchParams({api:'1',destination});
  if(origin)query.set('origin',origin);
  return 'https://www.google.com/maps/dir/?'+query.toString();
}

/** Defence in depth for legacy/imported data; link normalization belongs to the API. */
export function safeOpportunityLink(value?:string|null) {
  if(typeof value!=='string')return '';
  const candidate=value.trim();
  if(!candidate||candidate.length>2048||/[\s\u0000-\u001f\u007f\\]/.test(candidate))return '';
  try{
    const url=new URL(candidate);
    if(!['http:','https:'].includes(url.protocol)||!url.hostname||url.username||url.password)return '';
    return url.href;
  }catch{return ''}
}
