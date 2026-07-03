# Kubernetes manifests

Deploys the full DeepResearch stack to a cluster. Same images the CI builds; the
worker scales independently of the API.

## Layout

| File | What it deploys |
|------|-----------------|
| `namespace.yaml` | `deepresearch` namespace |
| `config.yaml` | `dr-config` ConfigMap (service URLs) + `dr-secrets` Secret (**placeholders**) |
| `mysql.yaml` / `redis.yaml` / `qdrant.yaml` / `kafka.yaml` | backing infra (StatefulSets with PVCs; Redis is a Deployment) |
| `backend.yaml` | API Deployment (+ migrate init container) and Service, with `/health` & `/ready` probes |
| `worker.yaml` | worker Deployment + CPU HorizontalPodAutoscaler (2→6) |
| `frontend.yaml` | frontend Deployment and Service |
| `ingress.yaml` | nginx Ingress — `/api` → backend, `/` → frontend (SSE buffering off) |
| `kustomization.yaml` | applies all of the above into the namespace |

## Prerequisites

- An ingress-nginx controller (for `ingress.yaml`).
- metrics-server (for the worker HPA).
- A default StorageClass (for the PVCs).
- Images published to a registry the cluster can pull (the names assume
  `ghcr.io/shivamchaubey14/research-agent-*`). For local clusters (kind/minikube)
  load the locally built images and keep `imagePullPolicy: IfNotPresent`.

## Deploy

```bash
# 1. Set real secrets first (do NOT commit them):
kubectl -n deepresearch create secret generic dr-secrets \
  --from-literal=DJANGO_SECRET_KEY="$(openssl rand -hex 32)" \
  --from-literal=GROQ_API_KEY="gsk_..." \
  --from-literal=TAVILY_API_KEY="" \
  --from-literal=MYSQL_ROOT_PASSWORD='root@123' \
  --from-literal=DATABASE_URL='mysql://root:root%40123@mysql:3306/research' \
  --dry-run=client -o yaml | kubectl apply -f -

# 2. Apply everything:
kubectl apply -k infra/k8s

# 3. Reach it (map the ingress host locally):
#   echo "127.0.0.1 deepresearch.local" >> /etc/hosts   # or the LB IP
#   open http://deepresearch.local
```

Validate without a cluster: `kubectl apply -k infra/k8s --dry-run=client`.

## Notes

- The Secret in `config.yaml` ships with **placeholder** values so the manifests
  are self-contained for dry-runs; override it (step 1) or use sealed-secrets /
  an external secret store in production.
- The frontend image runs the Vite dev server; a production build (`vite build`
  → nginx) is a Phase 8 polish item.
