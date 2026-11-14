{{- define "sam.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- define "sam.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 50 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "sam.name" .) | trunc 50 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- define "sam.labels" -}}
app.kubernetes.io/name: {{ include "sam.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}
{{- define "sam.selectorLabels" -}}
app.kubernetes.io/name: {{ include "sam.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}
{{- define "sam.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "sam.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}
{{- define "sam.secretEnv" -}}
{{- $secret := required "existingSecret must name a pre-created Secret" .Values.existingSecret -}}
{{- range $env, $key := .Values.secretKeys }}
- name: {{ $env }}
  valueFrom:
    secretKeyRef:
      name: {{ $secret | quote }}
      key: {{ $key | quote }}
{{- end -}}
{{- end -}}
