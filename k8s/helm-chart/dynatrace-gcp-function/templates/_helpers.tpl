// Copyright 2021 Dynatrace LLC

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     http://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.


{{/*
    Environment ID, taken from https://environment-id.live.dynatrace.com for SaaS and https://my.tenant.com/e/environment-id
*/}}
{{- define "environmentID" }}
  {{- with .Values }}
    {{- if contains "/e/" .dynatraceUrl -}}
      {{- printf "%s" (split "/e/" .dynatraceUrl)._1 }}
    {{- else -}}
      {{- printf "%s" (split "//" ((split "." .dynatraceUrl))._0)._1 }}
    {{- end -}}
  {{- end }}
{{- end }}

{{/*
    Creates base64 coded ./docker/config.json.
*/}}
{{- define "imagePullSecret" }}
{{- $name := (include "environmentID" .)}}
{{- with .Values }}
{{- printf  "{\"auths\":{\"%s\":{\"username\":\"%s\",\"password\":\"%s\",\"auth\":\"%s\"}}}" .dynatraceUrl $name .activeGate.dynatracePaasToken (printf "%s:%s" $name .activeGate.dynatracePaasToken | b64enc) | b64enc }}
{{- end }}
{{- end }}


{{/*
    Active Gate Docker image name. Taken from Dynatrace cluster. Example environment-id.live.dynatrace.com/linux/activegate.
*/}}
{{- define "activeGateImage" }}
{{- with .Values }}
{{- printf "%s/linux/activegate" (split "//" .dynatraceUrl)._1}}
{{- end }}
{{- end }}


{{/*
activeGateUrl in case of the .Values.activeGate.autoDeploy is
     ON (true) -> the  .Values.dynatraceLogIngestUrl is NOT used as an Active Gate URL. For log ingest. The URL is pointing to autodeployed AG inside k8s cluster.
     OFF (false) -> the  .Values.dynatraceLogIngestUrl IS used as an Active Gate URL. For log ingest. 
*/}}
{{- define "activeGateUrl" }}
{{- if .Values.activeGate.autoDeploy}}  
  {{- $envid := (include "environmentID" .)}}
  {{- printf "https://dynatrace-activegate-gcpmon-router.dynatrace.svc.cluster.local:%d/e/%s"  (int .Values.activeGate.autoDeployPort) $envid | quote}}    
{{- else -}}
  {{- printf "%s" .Values.dynatraceLogIngestUrl }}
{{- end -}}
   


{{- end }}


