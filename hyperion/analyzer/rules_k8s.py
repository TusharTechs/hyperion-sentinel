"""Kubernetes manifest rules."""

from __future__ import annotations

from ..models import CONFIRM_REQUIRED, MANUAL_ONLY, SAFE_AUTO
from .common import is_map, is_unpinned, line_of, mk, pin_suggestion, split_image

WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "Pod"}
DEFAULT_RESOURCES = {"requests": {"cpu": "100m", "memory": "128Mi"}, "limits": {"cpu": "500m", "memory": "256Mi"}}


def pod_spec_of(doc):
    kind = doc.get("kind")
    spec = doc.get("spec")
    if not is_map(spec):
        return None, None
    if kind == "Pod":
        return spec, ()
    if kind == "CronJob":
        jt = spec.get("jobTemplate")
        t = (jt.get("spec") or {}).get("template") if is_map(jt) else None
        return ((t or {}).get("spec"), ("spec", "jobTemplate", "spec", "template", "spec")) if is_map(t) else (None, None)
    t = spec.get("template")
    if is_map(t) and is_map(t.get("spec")):
        return t["spec"], ("spec", "template", "spec")
    return None, None


def analyze_k8s_doc(path: str, doc, doc_index: int):
    out = []
    kind, meta = doc.get("kind"), doc.get("metadata") if is_map(doc.get("metadata")) else {}
    name = str(meta.get("name", "?"))

    if kind == "Service":
        spec = doc.get("spec") or {}
        t = spec.get("type")
        if t in ("LoadBalancer", "NodePort"):
            out.append(mk("K8S-SVC-TYPE", "LOW", "kubernetes", path, f"Service `{name}` is exposed as {t}",
                          f"line {line_of(spec, 'type')}: type: {t}",
                          "LoadBalancer/NodePort publish the service outside the cluster; on edge sites that is often unintended and may not be supported.",
                          "Use ClusterIP plus an Ingress unless external exposure is required.",
                          CONFIRM_REQUIRED, line=line_of(spec, "type"), target=f"Service/{name}", doc_index=doc_index))
        return out

    if kind not in WORKLOADS:
        return out
    pod, ppath = pod_spec_of(doc)
    if pod is None:
        return out
    wl = f"{kind}/{name}"

    # replicas
    rep = (doc.get("spec") or {}).get("replicas")
    if kind == "Deployment" and isinstance(rep, int) and rep > 3:
        out.append(mk("K8S-REPLICAS", "LOW", "kubernetes", path, f"{wl} requests {rep} replicas",
                      f"line {line_of(doc['spec'], 'replicas')}: replicas: {rep}",
                      "Each replica consumes CPU/memory on a constrained site; more than 3 is rarely needed at the edge.",
                      "Reduce replicas to 2 unless you have measured a need for more.",
                      CONFIRM_REQUIRED, line=line_of(doc["spec"], "replicas"), target=wl, doc_index=doc_index, replicas=2))

    for flag, rule in (("hostNetwork", "K8S-HOSTNET"), ("hostPID", "K8S-HOSTPID"), ("hostIPC", "K8S-HOSTIPC")):
        if pod.get(flag) is True:
            out.append(mk(rule, "HIGH", "kubernetes", path, f"{wl} uses {flag}",
                          f"line {line_of(pod, flag)}: {flag}: true",
                          "Sharing the host namespace removes isolation between this pod and the node.",
                          f"Remove {flag} unless the workload truly needs it.", CONFIRM_REQUIRED,
                          line=line_of(pod, flag), target=f"{wl}:{flag}", doc_index=doc_index, flag=flag))

    if "nodeSelector" not in pod and "affinity" not in pod and kind in ("Deployment", "StatefulSet", "DaemonSet"):
        out.append(mk("K8S-PLACEMENT", "LOW", "kubernetes", path, f"{wl} has no nodeSelector or affinity",
                      "Neither nodeSelector nor affinity is set",
                      "With no placement hints the scheduler may place it on any node, including unsuitable devices.",
                      "Add a nodeSelector/affinity matching the intended edge node labels.", MANUAL_ONLY,
                      target=wl, doc_index=doc_index))

    pod_sc = pod.get("securityContext") if is_map(pod.get("securityContext")) else {}
    for ckey in ("initContainers", "containers"):
        for ci, c in enumerate(pod.get(ckey) or []):
            if not is_map(c):
                continue
            cname = str(c.get("name", f"#{ci}"))
            tgt = f"{wl}/{cname}"
            base = dict(target=tgt, doc_index=doc_index, container=ci, container_key=ckey)
            cl = line_of(c) or None
            img = c.get("image")
            if isinstance(img, str):
                _, tag = split_image(img)
                if is_unpinned(tag):
                    sug = pin_suggestion(img)
                    out.append(mk("K8S-LATEST", "MEDIUM", "kubernetes", path, f"{tgt} image is not pinned",
                                  f"line {line_of(c, 'image')}: image: {img}",
                                  "`latest`/untagged images make rollouts non-reproducible and can pull a different build per node.",
                                  "Pin a version" + (f", e.g. {sug}." if sug else "."),
                                  SAFE_AUTO if sug else MANUAL_ONLY, line=line_of(c, "image"), suggestion=sug, **base))
            if ckey != "containers":
                continue
            res = c.get("resources") if is_map(c.get("resources")) else {}
            req, lim = res.get("requests") or {}, res.get("limits") or {}
            miss_req = [k for k in ("cpu", "memory") if k not in req]
            miss_lim = [k for k in ("cpu", "memory") if k not in lim]
            if miss_req or miss_lim:
                gaps = []
                if miss_req:
                    gaps.append(f"requests ({'/'.join(miss_req)})")
                if miss_lim:
                    gaps.append(f"limits ({'/'.join(miss_lim)})")
                out.append(mk("K8S-RESOURCES", "HIGH", "kubernetes", path, f"{tgt} is missing resource " + " and ".join(gaps),
                              f"line {cl}: resources.requests/limits incomplete",
                              "Without requests the scheduler cannot reserve capacity, and without limits one container can exhaust the node's CPU or memory and starve its neighbours - both matter on small edge nodes.",
                              f"Add requests ({DEFAULT_RESOURCES['requests']['cpu']} CPU / {DEFAULT_RESOURCES['requests']['memory']}) and limits ({DEFAULT_RESOURCES['limits']['cpu']} CPU / {DEFAULT_RESOURCES['limits']['memory']}).",
                              SAFE_AUTO, line=cl, missing_requests=miss_req, missing_limits=miss_lim, **base))
            ports = [p.get("containerPort") for p in (c.get("ports") or []) if is_map(p) and p.get("containerPort")]
            for pk, rule, sev, why in (
                ("readinessProbe", "K8S-READINESS", "HIGH",
                 "Without a readiness probe, traffic can be routed to a pod before it can serve requests."),
                ("livenessProbe", "K8S-LIVENESS", "MEDIUM",
                 "Without a liveness probe, a hung container is never restarted automatically."),
            ):
                if pk not in c:
                    out.append(mk(rule, sev, "kubernetes", path, f"{tgt} has no {pk}",
                                  f"line {cl}: no {pk}", why,
                                  f"Add a {pk}" + (f" (tcpSocket on port {ports[0]})." if ports else " (declare containerPort first)."),
                                  SAFE_AUTO if ports else MANUAL_ONLY, line=cl, probe=pk,
                                  port=ports[0] if ports else None, **base))
            sc = c.get("securityContext") if is_map(c.get("securityContext")) else {}
            if sc.get("privileged") is True:
                out.append(mk("K8S-PRIVILEGED", "CRITICAL", "kubernetes", path, f"{tgt} runs privileged",
                              f"line {line_of(sc, 'privileged')}: privileged: true",
                              "A privileged container has near-root access to the host.",
                              "Set privileged: false and grant only the specific capabilities needed.",
                              CONFIRM_REQUIRED, line=line_of(sc, "privileged"), **base))
            non_root = sc.get("runAsNonRoot") is True or pod_sc.get("runAsNonRoot") is True or \
                isinstance(sc.get("runAsUser"), int) and sc["runAsUser"] > 0 or \
                isinstance(pod_sc.get("runAsUser"), int) and pod_sc["runAsUser"] > 0
            if not non_root:
                out.append(mk("K8S-NONROOT", "MEDIUM", "kubernetes", path, f"{tgt} may run as root",
                              f"line {cl}: no runAsNonRoot/runAsUser (container or pod level)",
                              "Containers default to the image's user, which is often root.",
                              "Set securityContext.runAsNonRoot: true and runAsUser: 10001.",
                              CONFIRM_REQUIRED, line=cl, **base))
    return out
