import{_ as a,l as s,I as o,e as i}from"./C3F3mMfW.js";import{p as g}from"./Nzbj-vFe.js";var p={parse:a(async r=>{const e=await g("info",r);s.debug(e)},"parse")},v={version:"11.15.0"},d=a(()=>v.version,"getVersion"),m={getVersion:d},c=a((r,e,n)=>{s.debug(`rendering info diagram
`+r);const t=o(e);i(t,100,400,!0),t.append("g").append("text").attr("x",100).attr("y",40).attr("class","version").attr("font-size",32).style("text-anchor","middle").text(`v${n}`)},"draw"),l={draw:c},_={parser:p,db:m,renderer:l};export{_ as diagram};
//# sourceMappingURL=B4r4_nrM.js.map
