# The Chaos Engineer's Mindset & Failure Catalog

## "There's Only So Much You Can Do" - Wrong.

The universe of failure modes is *vast*. Every layer of the stack can fail, every dependency can misbehave, every assumption can be violated. A chaos engineer's job is to systematically explore this space.

---

## The Failure Taxonomy

Think of your system as layers, each with its own failure modes:

```
┌─────────────────────────────────────────────────────────────────┐
│                        FAILURE LAYERS                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  LAYER 7: APPLICATION                                           │
│  ├── Logic errors, race conditions, memory leaks               │
│  ├── Deadlocks, infinite loops, thread starvation              │
│  └── Bad deployments, configuration drift                      │
│                                                                 │
│  LAYER 6: DEPENDENCIES                                          │
│  ├── Third-party API failures, rate limiting                   │
│  ├── Database unavailability, slow queries                     │
│  └── Cache failures, message queue backlogs                    │
│                                                                 │
│  LAYER 5: CONTAINER/PROCESS                                     │
│  ├── OOM kills, CPU throttling                                 │
│  ├── Container crashes, orchestrator failures                  │
│  └── Process hangs, zombie processes                           │
│                                                                 │
│  LAYER 4: NETWORK                                               │
│  ├── Latency spikes, packet loss, DNS failures                 │
│  ├── Network partitions, split-brain scenarios                 │
│  └── TLS certificate expiry, MTU issues                        │
│                                                                 │
│  LAYER 3: OPERATING SYSTEM                                      │
│  ├── Disk full, inode exhaustion                               │
│  ├── File descriptor limits, clock skew                        │
│  └── Kernel panics, driver failures                            │
│                                                                 │
│  LAYER 2: HARDWARE                                              │
│  ├── Disk failures, memory corruption                          │
│  ├── CPU failures, NIC failures                                │
│  └── Power supply failures, cooling failures                   │
│                                                                 │
│  LAYER 1: INFRASTRUCTURE                                        │
│  ├── Availability zone outages, region failures                │
│  ├── Data center fires, natural disasters                      │
│  └── Provider outages (AWS, GCP, etc.)                         │
│                                                                 │
│  LAYER 0: HUMAN                                                 │
│  ├── Misconfigurations, bad deploys                            │
│  ├── Accidental deletions, credential leaks                    │
│  └── Incident response failures                                │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## The Complete Failure Catalog

### 1. RESOURCE EXHAUSTION

These failures occur when systems run out of something:

| Resource | Chaos Injection Method | Real-World Cause |
|----------|------------------------|------------------|
| **CPU** | `stress --cpu 4` | Runaway process, crypto mining attack, bad regex |
| **Memory** | `stress --vm 2 --vm-bytes 1G` | Memory leak, large payload, cache stampede |
| **Disk Space** | `dd if=/dev/zero of=/tmp/fill bs=1M count=10000` | Log explosion, uncleared temp files |
| **Disk I/O** | `stress --io 4` | Backup running, RAID rebuild, noisy neighbor |
| **Inodes** | `mkdir -p /tmp/inodes && for i in {1..1000000}; do touch /tmp/inodes/$i; done` | Millions of small files |
| **File Descriptors** | Exhaust with socket connections | Connection leak, too many open files |
| **Network Bandwidth** | `iperf3` flood | DDoS, video streaming spike, backup traffic |
| **Connection Pool** | Hold connections without releasing | Slow queries, connection leak |
| **Thread Pool** | Block all worker threads | Long-running requests, deadlocks |

**Insight**: Resource exhaustion failures are often *gradual*. Systems degrade slowly, then collapse suddenly. Your chaos should test both states.

---

### 2. NETWORK CHAOS

Network failures are the most common in distributed systems:

| Failure Mode | Tool/Method | What It Simulates |
|--------------|-------------|-------------------|
| **Latency** | `tc qdisc add dev eth0 root netem delay 100ms` | Geographic distance, congestion |
| **Latency Variance** | `tc qdisc add dev eth0 root netem delay 100ms 50ms` | Jittery network |
| **Packet Loss** | `tc qdisc add dev eth0 root netem loss 5%` | Unstable WiFi, overloaded switches |
| **Packet Corruption** | `tc qdisc add dev eth0 root netem corrupt 1%` | Bad NIC, EMI interference |
| **Packet Reordering** | `tc qdisc add dev eth0 root netem reorder 25%` | Multiple network paths |
| **Packet Duplication** | `tc qdisc add dev eth0 root netem duplicate 1%` | Network misconfiguration |
| **Bandwidth Limit** | `tc qdisc add dev eth0 root tbf rate 1mbit` | Throttled connection |
| **DNS Failure** | Block DNS or return NXDOMAIN | DNS outage, misconfigured resolver |
| **DNS Latency** | Delay DNS responses | Overloaded DNS server |
| **Network Partition** | `iptables -A INPUT -s 10.0.0.0/8 -j DROP` | Network split, firewall misconfiguration |
| **Connection Timeout** | Drop packets silently (no RST) | Black hole, asymmetric routing |
| **Connection Refused** | Return RST immediately | Service down, port not open |
| **TLS Failure** | Invalid certificate, expired cert | Certificate expiry, CA outage |
| **MTU Issues** | Fragment packets incorrectly | Misconfigured network path |

**Insight**: Network failures are *partial* and *asymmetric*. Service A might reach B, but B can't reach A. Your chaos should test these scenarios.

---

### 3. DEPENDENCY FAILURES

External services fail in many ways:

| Failure Mode | How to Simulate | Impact |
|--------------|-----------------|--------|
| **Total Outage** | Block all traffic to dependency | Service unavailable |
| **Partial Outage** | Fail 50% of requests | Intermittent errors |
| **Slow Response** | Add 5-10 second delays | Timeout cascades |
| **Rate Limiting** | Return 429 responses | Throttled access |
| **Degraded Response** | Return partial/stale data | Data inconsistency |
| **Error Response** | Return 500/503 errors | Retry storms |
| **Malformed Response** | Return invalid JSON/data | Parse errors |
| **Hung Connection** | Accept connection, never respond | Socket exhaustion |
| **Authentication Failure** | Reject credentials | Access denied |
| **API Version Mismatch** | Return unexpected schema | Deserialization failures |
| **Poison Pill** | Return data that causes crash | Application failure |

**Insight**: Dependencies fail in ways their documentation doesn't cover. Always ask: "What if this returns garbage?"

---

### 4. STATE & DATA FAILURES

Data corruption and state issues:

| Failure Mode | How to Simulate | Real-World Cause |
|--------------|-----------------|------------------|
| **Stale Cache** | Prevent cache invalidation | Cache coherency bug |
| **Cache Stampede** | Clear cache + send traffic spike | Cache expiry + load spike |
| **Data Corruption** | Write invalid data to DB | Bug, race condition |
| **Referential Integrity** | Delete parent without children | Bad cascading delete |
| **Clock Skew** | Offset system clock | NTP failure, VM clock drift |
| **Split Brain** | Network partition between replicas | Consensus failure |
| **Replication Lag** | Delay replication between DB nodes | High write load |
| **Lock Contention** | Hold locks indefinitely | Long transactions |
| **Deadlock** | Create circular dependencies | Concurrent updates |
| **Message Replay** | Resend same messages | At-least-once delivery |
| **Message Loss** | Drop messages silently | Network partition |
| **Out-of-Order Messages** | Reorder message delivery | Async processing |

**Insight**: State failures are the hardest to test and the most damaging in production. Idempotency matters.

---

### 5. APPLICATION-LEVEL CHAOS

These require code changes or middleware:

| Failure Mode | How to Inject | Purpose |
|--------------|---------------|---------|
| **Exception Injection** | Throw random exceptions in code | Test error handling |
| **Latency Injection** | Add `sleep()` to critical paths | Test timeout handling |
| **Memory Pressure** | Allocate memory, don't free | Test OOM behavior |
| **GC Pauses** | Force garbage collection | Test pause tolerance |
| **Feature Flag Failure** | Toggle features randomly | Test flag fallbacks |
| **Configuration Changes** | Change config mid-request | Test hot reload |
| **Bad Deploy** | Deploy broken code intentionally | Test rollback procedures |
| **Credential Rotation** | Rotate credentials mid-operation | Test secret handling |

---

### 6. HUMAN & PROCESS FAILURES

The most common failure mode:

| Failure Mode | How to Test | Purpose |
|--------------|-------------|---------|
| **Runbook Accuracy** | Follow runbook exactly, note gaps | Validate documentation |
| **On-Call Response** | Page at 3 AM, measure response time | Test incident response |
| **Communication Failure** | Silence one team during incident | Test escalation paths |
| **Tool Unavailability** | Disable dashboards during incident | Test alternative diagnosis |
| **Permission Issues** | Revoke access to critical systems | Test access management |
| **Decision Paralysis** | Present ambiguous symptoms | Test triage processes |

**Insight**: Chaos engineering isn't just technical. Game days that test human response are crucial.

---

## The Chaos Engineer Mindset

### 1. ASSUME EVERYTHING WILL FAIL

```
Traditional Developer:       Chaos Engineer:
"If this works..."          "When this fails..."
"The API will return..."    "The API might return garbage, timeout, or lie..."
"The database is up..."     "The database could be up, slow, or returning stale data..."
```

### 2. QUESTION ALL ASSUMPTIONS

Every system has hidden assumptions. Find them:

| Assumption | Question | Experiment |
|------------|----------|------------|
| "DNS always works" | What if DNS fails? | Block DNS, corrupt responses |
| "Clocks are synchronized" | What if clock skew is 30 minutes? | Offset NTP |
| "Network is reliable" | What if 10% of packets drop? | tc netem loss |
| "Disk is fast" | What if IOPS drops 90%? | Throttle disk I/O |
| "Memory is infinite" | What if you hit memory limits? | Reduce container memory |
| "Config is correct" | What if config is stale? | Change config mid-operation |

### 3. THINK IN FAILURE DOMAINS

A failure domain is a set of components that fail together:

```
FAILURE DOMAIN EXAMPLES:

Single Host:
└── If this machine dies, what's affected?
    └── Just one container? One customer? Everyone?

Availability Zone:
└── If us-east-1a goes down, what's affected?
    └── Do we have replicas in us-east-1b?

Region:
└── If all of us-east-1 is offline, what happens?
    └── Do we failover to us-west-2?

Provider:
└── If AWS is down, what happens?
    └── Do we have multi-cloud fallback?

Dependency:
└── If Stripe is down, what happens?
    └── Can customers still browse? Still checkout?
```

### 4. DESIGN CHAOS FROM INCIDENTS

Every production incident is a free chaos experiment idea:

```
Incident: "Redis went down and took the whole site with it"
     ↓
Chaos Experiment: "What happens when Redis is unavailable?"
     ↓
Fix: "Add fallback to direct database queries"
     ↓
Re-run Chaos: "Verify fallback works"
```

### 5. GRADUATE BLAST RADIUS

```
Start:  Single host, synthetic traffic
  ↓
        Multiple hosts, synthetic traffic
  ↓
        Single host, 1% production traffic
  ↓
        Multiple hosts, 1% production traffic
  ↓
        Single AZ, 5% production traffic
  ↓
        Multiple AZs, 10% production traffic
  ↓
End:    Full region, 100% production traffic
```

### 6. ALWAYS HAVE A HYPOTHESIS

Bad chaos: "Let's kill the database and see what happens"
Good chaos: "I hypothesize that killing the primary database will cause a failover to the replica within 30 seconds, with fewer than 100 failed requests"

The hypothesis makes success/failure measurable.

### 7. SAFETY IS PARAMOUNT

```
CHAOS SAFETY CHECKLIST:

□ Stop conditions are defined and tested
□ Rollback procedure is documented and practiced
□ Blast radius is limited
□ Run during low-traffic periods initially
□ Team is aware and monitoring
□ Customer impact is understood and accepted
```

---

## Chaos Categories by AWS Service

For your NEMESIS project, here's what's possible:

### Lambda Chaos
- Throttle concurrency (block invocations)
- Timeout functions (set very short timeout)
- Inject latency (add sleep in code)
- Return errors (throw exceptions)
- Exhaust memory (allocate beyond limit)
- Cold start testing (force new containers)

### DynamoDB Chaos
- Throttle reads/writes (FIS or IAM deny)
- Inject latency (proxy with delay)
- Return errors (FIS inject-api-internal-error)
- Data corruption (write bad data)
- Global table replication delay

### S3 Chaos
- Access denied (IAM changes)
- Latency (hard to inject directly)
- 503 SlowDown responses (high load)
- Object versioning conflicts

### SQS Chaos
- Delay delivery (visibility timeout)
- Message loss (delete messages)
- Duplicate delivery (simulate at-least-once)
- Queue full (hit limits)
- DLQ overflow

### Network (VPC) Chaos
- Security group changes (block traffic)
- Network ACL changes (block subnets)
- Route table modifications
- NAT Gateway failure
- VPC Peering disruption

---

## Experiments You Should Build

### Beginner (Do These First)
1. **Service unavailable**: What if Lambda can't invoke?
2. **Dependency down**: What if DynamoDB is unreachable?
3. **Slow dependency**: What if DynamoDB takes 10 seconds to respond?

### Intermediate
4. **Partial failure**: What if 50% of DynamoDB requests fail?
5. **Cascade failure**: What if one Lambda failure triggers others?
6. **Resource exhaustion**: What if Lambda hits memory limits?

### Advanced
7. **Byzantine failure**: What if a service returns wrong but valid-looking data?
8. **Split brain**: What if two Lambda instances disagree about state?
9. **Clock skew**: What if timestamps are wrong?

### Expert
10. **Multi-failure**: What if Lambda AND DynamoDB have issues simultaneously?
11. **Recovery failure**: What if the recovery mechanism itself fails?
12. **Observability failure**: What if CloudWatch is down during an incident?

---

## The Chaos Engineer's Creed

```
I do not hope that systems won't fail.
I ensure they fail gracefully.

I do not trust that dependencies are reliable.
I verify they can be absent.

I do not assume the network works.
I prove the system survives when it doesn't.

I do not wait for incidents to happen.
I cause them intentionally, in controlled conditions.

I do not guess at system behavior.
I measure it under stress.

I do not fear failure.
I learn from it.
```

---

## Reading List

1. **"Chaos Engineering" by Casey Rosenthal** - The definitive book
2. **Netflix Chaos Engineering Blog** - Where it all started
3. **AWS FIS Documentation** - Service-specific chaos actions
4. **"Release It!" by Michael Nygard** - Stability patterns
5. **Google SRE Book** - Chapter on testing reliability
6. **Principlesofchaos.org** - The manifesto

---

## Summary

"There's only so much you can do" - **False**.

The failure space is enormous:
- 8+ layers of the stack can fail
- 50+ distinct failure modes per layer
- Failures combine in exponential ways
- Human factors multiply complexity

Your job as a chaos engineer: **Systematically explore this space before production does it for you.**

The difference between chaos engineering and hoping for the best is the difference between finding vulnerabilities in a controlled environment vs. discovering them at 3 AM during peak traffic with customers screaming.

Choose chaos.
