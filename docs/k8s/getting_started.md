## Quick start on Kubernetes

### Overview
It's possible to run monitoring as Kubernetes Container. In this case all configurations and secretes are stored as K8S ConfigMap / Secretes objects. 

*Architecture with Google Cloud Function deployment*
![GKE Container Architecture](/img/architecture-k8s.svg)


### Requirements 
* Google Cloud SDK [Google Cloud SDK installer](https://cloud.google.com/sdk/docs/downloads-interactive#linux)
* Kubernetes CLI [Install and setup kubectl](https://kubernetes.io/docs/tasks/tools/install-kubectl/) 
* `Workload identity` enabled on GKE Cluster [Enabling Workload Identity on a cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity#enable_on_cluster)
* `GKE_METADATA` enabled on GKE node pools [Enabling Workload Identity on a cluster](https://cloud.google.com/kubernetes-engine/docs/how-to/workload-identity#enable_on_cluster)

### Create Service Account & Kubernetes objects
Create `dynatrace` namespace with `kubectl`, and secrets for Dynatrace cluster `API token` and `URL`. 

Replace {DYNATRACE_URL} with URL to Your Dynatrace SaaS or Managed environment.

Replace {DYNATRACE_API_TOKEN} with  Dynatrace API token. You can learn how to generate token [Dynatrace API - Tokens and authentication](https://www.dynatrace.com/support/help/dynatrace-api/basics/dynatrace-api-authentication) manual. Integration requires `Ingest metrics using API V2` Token permission.
```
kubectl create namespace dynatrace
kubectl -n dynatrace create secret generic dynatrace-gcp-function-secret --from-literal="access-key={DYNATRACE_API_TOKEN}" --from-literal="url={DYNATRACE_URL}"
```

Create IAM Service Account with Cloud Shell and configure it for workload identity. Replace `{GCP-PROJECT-ID}` with your GCP project ID

```
gcloud iam service-accounts create dynatrace-gcp-function-sa

gcloud iam service-accounts add-iam-policy-binding --role roles/iam.workloadIdentityUser --member "serviceAccount:{GCP-PROJECT-ID}.svc.id.goog[dynatrace/dynatrace-gcp-function-sa]" dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com
```

Grant required IAM policies to Service Account. Replace `{GCP-PROJECT-ID}` with your GCP project ID
```
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/monitoring.editor
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/monitoring.viewer
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/compute.viewer
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/cloudsql.viewer
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/cloudfunctions.viewer
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/file.viewer
gcloud projects add-iam-policy-binding {GCP-PROJECT-ID} --member="serviceAccount:dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com" --role=roles/pubsub.viewer
```

Enable API's required for monitoring
```
gcloud services enable cloudapis.googleapis.com monitoring.googleapis.com cloudresourcemanager.googleapis.com
```


Download and install [dynatrace-gcp-function.yaml](k8s/dynatrace-gcp-function.yaml) Kubernetes objects:
```
wget https://raw.githubusercontent.com/dynatrace-oss/dynatrace-gcp-function/master/k8s/dynatrace-gcp-function.yaml
```
You can adjust the function behavior in `dynatrace-gcp-function-config` Config Map defined in dynatrace-gcp-function.yaml. 

Deploy Kubernetes objects:
```
kubectl apply -f dynatrace-gcp-function.yaml
```

Create annotation for service account. Replace `{GCP-PROJECT-ID}` with your GCP project ID:
```
kubectl annotate serviceaccount --namespace dynatrace dynatrace-gcp-function-sa iam.gke.io/gcp-service-account=dynatrace-gcp-function-sa@{GCP-PROJECT-ID}.iam.gserviceaccount.com
```

Check the container status:
```
kubectl -n dynatrace logs -l app=dynatrace-gcp-function
```
Logs should output overall status of each metrics pull execution:
```
Starting download of metadata for service 'cloudsql_database'
Download of metadata for service 'pubsub_subscription' finished
Download of metadata for service 'cloudsql_database' finished
Download of metadata for service 'filestore_instance' finished
Download of metadata for service 'cloud_function' finished
Fetched GCP data in 1.1237902641296387 s
Ingest response: {'linesOk': 421, 'linesInvalid': 0, 'error': None}
Finished uploading metric ingest lines to Dynatrace in 0.36574411392211914 s
Pushing self monitoring time series to GCP Monitor...
Finished pushing self monitoring time series to GCP Monitor
```


### Extend monitoring scope
...

### Troubleshoot and support
#### I can not see metrics in Dynatrace...
If you are having issues running `K8s`
...