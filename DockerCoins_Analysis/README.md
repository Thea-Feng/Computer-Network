[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-24ddc0f5d75046c5622901739e7c5dd533143b0c8e959d652212380cedb1ea36.svg)](https://classroom.github.com/a/OxtFVEbX)
# CSC4303/CSC6203 Assignment 5

### Deadline: April 28, 2024, 23:59

### Name: Yutong Feng

### Student ID: 120090266

---

## DockerCoins

- DockerCoins is made of 5 services
  - `rng` = web service generating random bytes
  - `hasher` = web service computing hash of POSTed data
  - `worker` = background process calling `rng` and `hasher`
  - `webui` = web interface to watch progress
  - `redis` = data store (holds a counter updated by `worker`)

![](https://raw.githubusercontent.com/cuhksz-csc4303-24s/assets/main/dockercoins.png)

In this assignment, you will deploy an application called `DockerCoins` which generates a few random bytes, hashes these bytes, increments a counter (to keep track of speed) and repeats forever! You will try to find its bottlenecks when scaling and use HPA (Horizontal Pod Autoscaler) to scale the application. Please follow these instructions carefully!

## Environment Setup

The assignment needs to be setup in `AWS`. You should choose `Ubuntu Server 22.04 LTS (HVM), SSD Volume Type` as AMI (Amazon Machine Image) and `m4.large` as the instance type. And you need to configure security group as followed, to make sure that you can access the service of minikube on the web browser later.

| Type        | Protocol | Port Range | Source    | Description |
| ----------- | -------- | ---------- | --------- | ----------- |
| All traffic | All      | All        | 0.0.0.0/0 |             |

Run the following commands to satisfy the requirements.

```bash
# Install Minikube
$ curl -LO https://storage.googleapis.com/minikube/releases/latest/minikube-linux-amd64
$ sudo install minikube-linux-amd64 /usr/local/bin/minikube

# Install kubectl
$ curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl"
$ sudo install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl

# Install Docker
$ sudo apt-get update && sudo apt-get install docker.io -y

# Install conntrack
$ sudo apt-get install -y conntrack

# Install httping
$ sudo apt-get install httping

# Install Helm
$ curl -fsSL -o get_helm.sh https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3
$ chmod 700 get_helm.sh
$ ./get_helm.sh
```

## Running Minikube on EC2 Ubuntu

Add user to “docker” group and switch primary group

```bash
$ sudo usermod -aG docker $USER && newgrp docker
```

### Start Minikube

```bash
$ minikube start
```

## Start the application

You can `git clone` the assignment repo and `cd` into this directory.

- Start the application from the `dockercoins` yaml

```bash
$ kubectl apply -f dockercoins.yaml
```

- Wait until all the components are running

```bash
$ kubectl get po
# NAME                     READY   STATUS    RESTARTS   AGE
# hasher-89f59d444-r7v7j   1/1     Running   0          27s
# redis-85d47694f4-m8vnt   1/1     Running   0          27s
# rng-778c878fb8-ch7c2     1/1     Running   0          27s
# webui-7dfbbf5985-24z79   1/1     Running   0          27s
# worker-949969887-rkn48   1/1     Running   0          27s
```

- Check the results from UI

```bash
$ minikube service webui
# |-----------|-------|-------------|----------------------------|
# | NAMESPACE | NAME  | TARGET PORT |            URL             |
# |-----------|-------|-------------|----------------------------|
# | default   | webui |          80 | http://172.31.67.128:30163 |
# |-----------|-------|-------------|----------------------------|
# 🎉  Opening service default/webui in default browser...
# 👉  http://172.31.67.128:30163
```

- Port forwarding for WebUI

You need to forward connections to a local port to a port on the pod.

```bash
$ kubectl port-forward --address 0.0.0.0 <webui pod name> <local port>:<pod port>
```

Local port is any number. Pod Port is target port (e.g., 80).

You can access the DockerCoin Miner WebUI on a web browser. The address is &lt;Public IPv4 address&gt;:&lt;local port&gt; (e.g., `3.238.254.199`:`30163`, where `3.238.254.199` is Public IPv4 address of the instance).

_Note_: kubectl port-forward does not return. To continue with the exercises, you will need to open another terminal.

![](https://raw.githubusercontent.com/cuhksz-csc4303-24s/assets/main/webui.png)

## Bottleneck detection

### Workers

Scale the # of workers from 2 to 10 (change the number of `replicas`).

```bash
$ kubectl scale deployment worker --replicas=3
```

| # of workers  | 1   | 2   | 3   | 4   | 5   | 10  |
| ------------- | --- | --- | --- | --- | --- | --- |
| hashes/second |  4.0   |  7.0   |  10.0   |  12   |   8  |  10   |

> Question: What is the speedup bump when you have 10x workers?
> 
> Answer: About 2.5x compareed to 1 work.

### Rng / Hasher

Keep the number of workers as `10`. Note that, `rng` or `hasher` service is a bottleneck.

To identify which one is the bottleneck, you can use `httping` command for latency detection.

```bash
# Expose the service, since we are detecting the latency outside the k8s cluster
$ kubectl expose service rng --type=NodePort --target-port=80 --name=rng-np
$ kubectl expose service hasher --type=NodePort --target-port=80 --name=hasher-np

# Get the url of the service
$ kubectl get svc rng-np hasher-np

# Find the minikube address
$ kubectl cluster-info
# Kubernetes control plane is running at https://172.31.67.128:8443
# KubeDNS is running at https://172.31.67.128:8443/api/v1/namespaces/kube-system/services/kube-dns:dns/proxy
# Here, minikube address is 172.31.67.128

# Detect the latency of hasher
$ httping <minikube-address>:<hasher-np-port>

# Detect the latency of rng
$ httping <minikube-address>:<rng-np-port>
```

| Service      | Hasher | Rng |
| ------------ | ------ | --- |
| Latency (ms) |   1.4     |   731  |

> Question: Which service is the bottleneck?
>
> Answer: Rng

## HPA

To solve the bottleneck of the application, you can specify a horizontal pod autoscaler which can scale the number of Pods based on some metrics.

```bash
# Install prometheus
$ helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
$ helm install prometheus prometheus-community/prometheus

# Expose service port
$ kubectl expose service prometheus-server --type=NodePort --target-port=9090 --name=prometheus-server-np
$ minikube service prometheus-server-np
```

Set a HPA service and export the latency for further hpa measurement. (Please replace `<FILL IN>` in the `httplat` yaml as which you need).

```bash
$ kubectl apply -f httplat.yaml
$ kubectl expose deployment httplat --port=9080

# Check if the deployment is ready
$ kubectl get deploy httplat
# NAME      READY   UP-TO-DATE   AVAILABLE   AGE
# httplat   1/1     1            1           43s
```

Configure Prometheus to gather the detected latency.

```bash
$ kubectl annotate service httplat \
          prometheus.io/scrape=true \
          prometheus.io/port=9080 \
          prometheus.io/path=/metrics
```

Connect to Prometheus

```bash
$ kubectl get svc prometheus-server-np
# NAME                   TYPE       CLUSTER-IP     EXTERNAL-IP   PORT(S)        AGE
# prometheus-server-np   NodePort   10.96.122.34   <none>        80:24057/TCP   87s
```

- Port forwarding for Prometheus UI

You need to forward connections to a local port to a port on the pod.

```bash
$ kubectl port-forward --address 0.0.0.0 <prometheus server pod name> <local port>:9090
```

To retrieve the Prometheus server pod name, type the following command into your terminal:

```bash
$ kubectl get po
```

The pod name you're looking for begins with `prometheus-server-`, such as `prometheus-server-8444b5b7f7-hk6g7`.

- Access Prometheus

You can access the Prometheus on a web browser. The address is &lt;Public IPv4 address&gt;:&lt;local port&gt;. Check if `httplab` metrics are available. You can try to graph the following PromQL expression.

```sql
rate(httplat_latency_seconds_sum[2m])/rate(httplat_latency_seconds_count[2m])
```

![](https://raw.githubusercontent.com/cuhksz-csc4303-24s/assets/main/prometheus.png)

### Create the autoscaling policy.

Your metric-server add on is disabled by default. Check it using:

```bash
$ minikube addons list
```

If its disabled, you will see something like metrics-server: disabled
Enable it using:

```bash
$ minikube addons enable metrics-server
```

Please replace `<FILL IN>` in the `hpa` yaml as which you need, then type the following command into your terminal:

```bash
$ kubectl apply -f hpa.yaml
```

The horizontal pod autoscaler in `hpa.yaml` is designed to automatically adjust the number of replicas for a particular deployment (that you need to `<FILL IN>`, either rng or hasher) based on CPU utilization. It ensures the number of replicas stays between 1 and 10, while aiming to have average CPU utilization of 5%. It uses a stabilization window of 10 seconds for scaling up and 30 seconds for scaling down.

Let's see the details of our hpa. If you still see `<unknown> / 5%`, try to wait for a while.

```bash
$ kubectl describe hpa <FILL IN> # FILL IN: rng or hasher
```

Now let's open three terminals:

1. Do port forwarding for Prometheus UI
2. Continuously watch our HPA (for rng or hasher) and provide real-time updates

```bash
$ kubectl get hpa <FILL IN> --watch # FILL IN: rng or hasher
```

3. Generate load test (for rng or hasher)

```bash
kubectl run -i --tty load-generator --rm --image=busybox:1.28 --restart=Never -- /bin/sh -c "while sleep 0.001; do wget -q -O- http://<FILL IN>; done" # FILL IN: rng or hasher
```

> **Screenshot** the performance graph in Prometheus UI, after setting up the HPA.
> <img src="screenshot.jpg">
> We can estimate performance by latency with the PromQL expression we used before.

```sql
rate(httplat_latency_seconds_sum[2m])/rate(httplat_latency_seconds_count[2m])
```

> **Open question**: Apart from the autoscaling policy we provided, think about how to reduce the fluctuation of the HPA:
>
> - Multiple HPAs to scale the pod?
> - Other metrics?
>
> Explain your method in details and show how you setup your own HPA.
>
> Answer: method:fine-tuning metric thresholds
> 
> Step 1: Determine Application’s Baseline
> Monitoring CPU and memory consumption under idle conditions.
Loading the application with increasing amounts of simulated traffic and observing resource usage and response times. This data helps determine reasonable threshold values for scaling that minimize unnecessary scaling events while ensuring the application can handle incoming requests.
>
> Step 2: Deploy Application on Kubernetes
> build a simple deployment manifest named myapp-deployment.yaml which is similar to httplat.yaml
>
> Step 3: Apply HPA with Initial Metric Thresholds
> Create an HPA manifest that targets the deployment. Here’s an example myapp-hpa.yaml targeting CPU utilization:
```
apiVersion: autoscaling/v2beta2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 1
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 50
```

> Apply the deployment and HPA:
```
kubectl apply -f myapp-deployment.yaml
kubectl apply -f myapp-hpa.yaml
```
> Step 4: Fine-Tune Metric Thresholds
```
kubectl get hpa myapp-hpa -o yaml
kubectl describe hpa myapp-hpa
```
>These commands provide information on current replicas, target and current metrics, and events related to scaling actions.
>
>If we notice unnecessary scaling actions (too many scale-ups/downs in short periods), we can adjust the averageUtilization value in HPA manifest. For instance, if our application can handle more load without degrading performance, we might increase the target CPU utilization to 70.
>
>Similarly, if we’re monitoring custom metrics like request latency or queue depth, adjust the target thresholds based on observed application performance and tolerance for latency or backlog.

**Optional**:

- Explore custom metrics (what we've been using is resource metric).
- Submit the `.yaml` file with your new autoscaling policy.

## Grading

In this assignment, you are required to finish the following things (each for 2 marks):

- Report the performance of DockerCoins with different number of workers.
- Detect latency and find the bottleneck component (rng or hasher).
- Upload the screenshot which shows the performance graph after setting up the HPA.
- Open question: How to reduce the fluctuation of the HPA?