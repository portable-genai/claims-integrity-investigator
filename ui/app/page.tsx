"use client";

import { useEffect, useState } from "react";

// Every request goes to THIS origin. The browser never learns the service's address and never
// holds its credential; the route handler under /api/agent forwards, having discarded whatever
// identity the client tried to assert.
const API = "/api/agent";

// Mirrors the service's seeded local personas. The picker is a DEV convenience: the server
// validates the selection against its own list, so a hand-crafted value cannot invent a persona.
const PERSONAS = ["analyst", "approver", "auditor", "other-tenant"];

// What happened to the human-review hand-off, in the words the user needs. A result that
// escalated but is not queued must say so rather than read as reviewed.
const REVIEW_ROUTING_TEXT: Record<string, string> = {
  routed: "Sent to the review console.",
  failed: "Could not reach the review console; this claim is not queued for review.",
  off: "Review routing is off in this deployment; this claim is not queued for review.",
};

function reviewRoutingOf(body: string): string | undefined {
  try {
    const parsed = JSON.parse(body) as { review_routing?: unknown };
    return typeof parsed.review_routing === "string" ? parsed.review_routing : undefined;
  } catch {
    return undefined;
  }
}

// The claim files the local profile seeds for the personas' tenant (FICTIONAL). There is no list
// endpoint for claims: `POST /v1/assess` takes a claim id and fetches the file server-side, so
// these are suggestions for the id field, not a catalogue. Another deployment's ids are typed in.
const SEEDED_CLAIMS = [
  { claim_id: "CLM-1001", subject: "Ravi Kumar (FICTIONAL), home contents water damage" },
  { claim_id: "CLM-1002", subject: "Mei Ling (FICTIONAL), home contents flood" },
  { claim_id: "CLM-1003", subject: "Jordan Blake (FICTIONAL), tools theft from a van" },
  { claim_id: "CLM-1004", subject: "Priya Nair (FICTIONAL), motor collision with injury" },
];

// One row of the review queue, as `GET /v1/siu-queue` returns it: the assessments this process
// has routed to human review, scoped to the persona's own tenant.
interface QueueItem {
  claim_id: string;
  subject: string;
  recommendation: string;
  severity: string;
}

interface CardSummary {
  name?: string;
  description?: string;
  skills?: { id: string; name: string }[];
}

export default function Home() {
  const [persona, setPersona] = useState(PERSONAS[0]);
  const [claimId, setClaimId] = useState(SEEDED_CLAIMS[3].claim_id);
  const [queue, setQueue] = useState<QueueItem[] | null>(null);
  const [queueError, setQueueError] = useState("");
  const [queueRead, setQueueRead] = useState(0);
  const [result, setResult] = useState("");
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [card, setCard] = useState<CardSummary | null>(null);

  // The service names itself, so this UI carries no hardcoded product name to go stale.
  useEffect(() => {
    let live = true;
    fetch(API + "/.well-known/agent-card.json", { cache: "no-store" })
      .then((response) => (response.ok ? response.json() : null))
      .then((body) => {
        if (live) setCard(body as CardSummary | null);
      })
      .catch(() => undefined);
    return () => {
      live = false;
    };
  }, []);

  // The review queue is the persona's own tenant's, so it is re-read whenever the persona changes,
  // and again after every assessment, because every assessment is routed to human review.
  useEffect(() => {
    let live = true;
    setQueueError("");
    fetch(API + "/v1/siu-queue", { cache: "no-store", headers: { "X-Dev-Persona": persona } })
      .then(async (response) => {
        if (!response.ok) throw new Error(response.status + " " + (await response.text()));
        return (await response.json()) as QueueItem[];
      })
      .then((items) => {
        if (live) setQueue(items);
      })
      .catch((error: unknown) => {
        if (live) setQueueError(String(error));
      });
    return () => {
      live = false;
    };
  }, [persona, queueRead]);

  useEffect(() => {
    setResult("");
  }, [persona]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailed(false);
    try {
      const response = await fetch(API + "/v1/assess", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Dev-Persona": persona },
        body: JSON.stringify({ claim_id: claimId.trim() }),
      });
      const body = await response.text();
      setFailed(!response.ok);
      setResult(body);
      setQueueRead((count) => count + 1);
    } catch (error) {
      setFailed(true);
      setResult(String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>{card?.name ?? "Agent console"}</h1>
      <p className="sub">
        {card?.description ??
          "Assess a claim by id. The recommendation is deterministic, cited, and routed to a human reviewer."}
      </p>

      <form onSubmit={submit}>
        <fieldset>
          <legend>Who you are</legend>
          <label>
            Seeded dev persona (local profile only; the server resolves identity, not this field)
            <select value={persona} onChange={(event) => setPersona(event.target.value)}>
              {PERSONAS.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        </fieldset>

        <fieldset>
          <legend>The claim</legend>
          <label>
            Claim id (the claimant, policy and documents are fetched server-side)
            <input
              value={claimId}
              list="seeded-claims"
              onChange={(event) => setClaimId(event.target.value)}
            />
            <datalist id="seeded-claims">
              {SEEDED_CLAIMS.map((claim) => (
                <option key={claim.claim_id} value={claim.claim_id}>
                  {claim.subject}
                </option>
              ))}
            </datalist>
          </label>
          <p className="sub">
            Seeded on the local profile:{" "}
            {SEEDED_CLAIMS.map((claim) => claim.claim_id).join(", ")}.
          </p>
          <button type="submit" disabled={busy || !claimId.trim()}>
            {busy ? "Working" : "Assess this claim"}
          </button>
        </fieldset>
      </form>

      {result && REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""] ? (
        <p className="sub" data-review-routing={reviewRoutingOf(result)}>
          {REVIEW_ROUTING_TEXT[reviewRoutingOf(result) ?? ""]}
        </p>
      ) : null}
      {result ? <pre className={failed ? "result error" : "result"}>{result}</pre> : null}

      <fieldset>
        <legend>Review queue</legend>
        {queueError ? <p className="result error">Could not read the review queue: {queueError}</p> : null}
        {queue && queue.length === 0 ? (
          <p className="sub">Nothing routed to review in this persona&apos;s tenant yet.</p>
        ) : null}
        {queue && queue.length > 0 ? (
          <ul>
            {queue.map((item, index) => (
              <li key={item.claim_id + ":" + index}>
                {item.claim_id}: {item.subject}, {item.recommendation} ({item.severity})
              </li>
            ))}
          </ul>
        ) : null}
      </fieldset>

      <footer>
        Synthetic, obviously fictional data only. Identity is resolved server-side and the
        client-asserted actor is discarded; see ui/README.md for the embedding contract.
      </footer>
    </main>
  );
}
