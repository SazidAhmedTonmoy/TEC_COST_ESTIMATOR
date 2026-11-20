import {useCallback,useEffect,useRef,useState} from 'react';
import {apiFetch} from '../main';
import type {BuilderContactGroup} from '@/lib/builder-contacts';

export const BUILDER_CONTACTS_CHANGED='tenders:builder-contacts-changed';
export function notifyBuilderContactsChanged(){window.dispatchEvent(new Event(BUILDER_CONTACTS_CHANGED))}

/** A fresh directory never replaces an in-progress contact draft. */
export function useBuilderContactDirectory(enabled=true){
  const [builders,setBuilders]=useState<BuilderContactGroup[]>([]);
  const [loading,setLoading]=useState(false),[error,setError]=useState('');
  const request=useRef<AbortController|null>(null);
  const refresh=useCallback(async()=>{
    if(!enabled)return;
    request.current?.abort();const controller=new AbortController();request.current=controller;
    setLoading(true);setError('');
    try{
      const response=await apiFetch('builder-contacts',{signal:controller.signal});
      const data=await response.json();if(!response.ok)throw Error(data.error||'Unable to load builder contacts.');
      if(!controller.signal.aborted)setBuilders(Array.isArray(data.builders)?data.builders:[]);
    }catch(e){if(!controller.signal.aborted)setError((e as Error).message)}
    finally{if(!controller.signal.aborted)setLoading(false)}
  },[enabled]);
  useEffect(()=>{
    if(!enabled){request.current?.abort();setLoading(false);return}
    void refresh();
    const update=()=>void refresh();
    window.addEventListener(BUILDER_CONTACTS_CHANGED,update);
    window.addEventListener('focus',update);
    return()=>{request.current?.abort();window.removeEventListener(BUILDER_CONTACTS_CHANGED,update);window.removeEventListener('focus',update)};
  },[enabled,refresh]);
  return {builders,loading,error,refresh};
}
