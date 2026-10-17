(() => {
  const $ = (id) => document.getElementById(id);
  const csrf = () => document.cookie.split("; ").find((x) => x.startsWith("csrftoken="))?.split("=")[1] || "";
  const iceConfig = document.getElementById("ice-servers-data")?.textContent || "[]";
  const iceServers = JSON.parse(iceConfig);
  let pc = null, stream = null, sessionId = null, pollTimer = null, seenRemote = new Set(), answerApplied = false;
  const api = (suffix="") => `/api/sessions/${sessionId}/${suffix}`;
  const status = (value) => { $("connection").textContent = value; };
  const message = (value, error=false) => { $("message").textContent = value; $("message").classList.toggle("error", error); };
  const jsonFetch = async (url, options={}) => {
    const response = await fetch(url, { ...options, headers: { "Content-Type":"application/json", "X-CSRFToken":csrf(), ...(options.headers||{}) } });
    const data = await response.json().catch(() => ({})); if (!response.ok) throw new Error(data.error || `Request failed (${response.status})`); return data;
  };
  const close = () => { clearInterval(pollTimer); pollTimer=null; pc?.close(); pc=null; stream?.getTracks().forEach(t=>t.stop()); stream=null; };
  const stopBroadcast = async () => { if(sessionId) await jsonFetch(api(),{method:"PATCH",body:JSON.stringify({status:"stopped"})}).catch(()=>{}); close(); sessionId=null; $("mic-button").classList.remove("active"); $("mic-title").textContent="Start microphone"; $("share-box").hidden=true; status("Ready"); message("Microphone session stopped. The mic is off."); };
  const exchangeCandidates = async () => {
    const result=await jsonFetch(api("candidates/receiver/"));
    for(const row of result.candidates) if(!seenRemote.has(row.id)){seenRemote.add(row.id);try{await pc.addIceCandidate(JSON.parse(row.candidate));}catch(e){if(!String(e).includes("remote description"))throw e;}}
  };
  const startBroadcast = async () => {
    if(sessionId){await stopBroadcast();return;}
    try{
      if(!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone access requires HTTPS or localhost.");
      status("Requesting microphone"); stream=await navigator.mediaDevices.getUserMedia({audio:true,video:false});
      const created=await jsonFetch("/api/sessions/",{method:"POST",body:"{}"}); sessionId=created.sessionId; seenRemote=new Set(); answerApplied=false;
      pc=new RTCPeerConnection({iceServers});
      pc.onicecandidate=(event)=>{if(event.candidate)jsonFetch(api("candidates/sender/"),{method:"POST",body:JSON.stringify({candidate:JSON.stringify(event.candidate.toJSON())})}).catch(e=>message(e.message,true));};
      pc.onconnectionstatechange=()=>status(pc?.connectionState||"Ready");
      stream.getAudioTracks().forEach(track=>pc.addTrack(track,stream));
      const offer=await pc.createOffer(); await pc.setLocalDescription(offer);
      await jsonFetch(api(),{method:"PATCH",body:JSON.stringify({offer:JSON.stringify(pc.localDescription),status:"offered"})});
      $("share-code").textContent=sessionId; $("share-box").hidden=false; $("mic-button").classList.add("active"); $("mic-title").textContent="Microphone is live"; status("Waiting for AirGuard app"); message("Enter this code in AirGuard Parent → Website Mic Listener.");
      pollTimer=setInterval(async()=>{try{const data=await jsonFetch(api());if(data.answer&&!answerApplied){await pc.setRemoteDescription(JSON.parse(data.answer));answerApplied=true;status("Connected to AirGuard");}if(answerApplied)await exchangeCandidates();}catch(e){message(e.message,true);}},1000);
    }catch(e){close();sessionId=null;status("Ready");message(e.message||"Could not start microphone.",true);}
  };
  $("mic-button").addEventListener("click",startBroadcast);
  $("copy-link").addEventListener("click",async()=>{await navigator.clipboard.writeText(`${location.origin}/`);message("Website address copied. Share the session code separately.");});
  // Request permission when the page opens, then release the probe stream.
  // The center button starts the actual audio broadcast.
  if (!navigator.mediaDevices?.getUserMedia) {
    message("This browser cannot request microphone access. Open this HTTPS page in Chrome or Safari.", true);
  } else {
    navigator.mediaDevices.getUserMedia({audio:true,video:false})
      .then(s=>{s.getTracks().forEach(t=>t.stop());message("Microphone permission is ready. Press the center button to send audio to AirGuard Parent.");})
      .catch(()=>message("Microphone permission was denied or blocked. Allow it in this site’s browser settings, then reload.",true));
  }
})();
