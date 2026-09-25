// Begin the authenticated data request while the application bundle loads.
window.__tenderBoot=fetch('/api/tenders/bootstrap').catch(function(){return null;});
