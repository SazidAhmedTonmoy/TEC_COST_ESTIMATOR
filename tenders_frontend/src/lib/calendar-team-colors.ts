/** Stable, accessible team colours for approved deadlines that need quoting. */
export type CalendarTeam={id:number;name:string};
export type CalendarTeamColor={accent:string;lightBg:string;lightFg:string;darkBg:string;darkFg:string};
export const TEAM_CALENDAR_COLORS:readonly CalendarTeamColor[]=[
  {accent:'#60a5fa',lightBg:'#dbeafe',lightFg:'#1e40af',darkBg:'#1d3558',darkFg:'#dbeafe'},
  {accent:'#c084fc',lightBg:'#f3e8ff',lightFg:'#6b21a8',darkBg:'#3c2955',darkFg:'#f3e8ff'},
  {accent:'#fb923c',lightBg:'#ffedd5',lightFg:'#9a3412',darkBg:'#50331e',darkFg:'#ffedd5'},
  {accent:'#fb7185',lightBg:'#ffe4e6',lightFg:'#9f1239',darkBg:'#562b3d',darkFg:'#ffe4e6'},
  {accent:'#2dd4bf',lightBg:'#ccfbf1',lightFg:'#115e59',darkBg:'#194943',darkFg:'#ccfbf1'},
  {accent:'#818cf8',lightBg:'#e0e7ff',lightFg:'#3730a3',darkBg:'#30365f',darkFg:'#e0e7ff'},
  {accent:'#eab308',lightBg:'#fef9c3',lightFg:'#854d0e',darkBg:'#51411b',darkFg:'#fef9c3'},
  {accent:'#38bdf8',lightBg:'#e0f2fe',lightFg:'#075985',darkBg:'#1b4055',darkFg:'#e0f2fe'},
];
const UNASSIGNED_COLOR:CalendarTeamColor={accent:'#94a3b8',lightBg:'#e2e8f0',lightFg:'#334155',darkBg:'#334155',darkFg:'#f1f5f9'};

/** New IDs receive new colours without recolouring older teams after renames. */
export function calendarTeamPalette(teams:CalendarTeam[]):Map<number,CalendarTeamColor>{
  const ids=[...new Set(teams.map(team=>team.id).filter(id=>Number.isSafeInteger(id)&&id>=0))].sort((a,b)=>a-b);
  return new Map(ids.map((id,i)=>[id,TEAM_CALENDAR_COLORS[i%TEAM_CALENDAR_COLORS.length]]));
}
export function teamCalendarColor(id:number|null,palette:Map<number,CalendarTeamColor>):CalendarTeamColor{
  return id===null?UNASSIGNED_COLOR:(palette.get(id)||UNASSIGNED_COLOR);
}
/** For multiply assigned projects, colour the lowest-ID team and name them all. */
export function calendarTeamAppearance(assigned:number[]|undefined,teams:CalendarTeam[],palette=calendarTeamPalette(teams)){
  const names=new Map(teams.map(team=>[team.id,team.name]));
  const ids=[...new Set((assigned||[]).filter(id=>names.has(id)))].sort((a,b)=>a-b);
  const primary=ids[0]??null;
  return {key:primary===null?'unassigned':String(primary),
    label:ids.length?ids.map(id=>names.get(id)).join(' · '):'Unassigned',
    color:teamCalendarColor(primary,palette),teamIds:ids};
}
