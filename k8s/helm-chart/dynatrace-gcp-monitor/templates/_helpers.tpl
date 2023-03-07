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
optional activeGateUrl for log ingestion. In case of the .Values.dynatraceLogIngestUrl is not set, .Values.dynatraceUrl is used.
*/}}
{{- define "activeGateUrl" }}
  {{- if eq .Values.dynatraceLogIngestUrl "" }}
    {{- printf "%s" .Values.dynatraceUrl }}
  {{- else }}
    {{- printf "%s" .Values.dynatraceLogIngestUrl }}
  {{- end -}}
{{- end }}

{{- define "activeGateHost" }}
  {{- $agurl := (include "activeGateUrl" .)}}
  {{- printf "%s" (split "/" (split "//" $agurl)._1)._0  }}
{{- end }}

{{/*
noProxyUrls is used in case of the .Value.useProxy is set ALL, DT_ONLY or GCP_ONLY
  In a case we are using an existing AG and the proxy should be used only for GCP then the communication between Function and AG must not use the proxy.
  In a case we are using an existing AG and the proxy should be used only for DT.
*/}}
{{- define "noProxyUrls"}}
  {{- if eq .Values.useProxy "GCP_ONLY" -}}
    {{- printf "metadata.google.internal,%s" (include "activeGateHost" .) }}
  {{- else if eq .Values.useProxy "DT_ONLY" }}
    {{- printf "metadata.google.internal,.googleapis.com" }}
  {{- else }}
    {{- printf "metadata.google.internal" }}
  {{- end -}}
{{- end }}
