/* global React, ReactDOM */
const { useState, useEffect, useRef, useCallback } = React;

// ─── Helpers ────────────────────────────────────────────────────────────────

let _msgId = 0;
function mkMsg(type, content) {
  return { id: String(++_msgId), type, content };
}

// ─── Phase progress bar ──────────────────────────────────────────────────────

function PhaseBar({ phase }) {
  const PHASES = ["profile", "criteria", "retrieval", "scoring", "complete"];
  const LABELS = {
    profile: "Profile", criteria: "Criteria",
    retrieval: "Retrieval", scoring: "Scoring", complete: "Complete",
  };
  const cur = PHASES.indexOf(phase);
  return (
    <div className="flex items-center gap-1 text-xs select-none">
      {PHASES.map((p, i) => (
        <React.Fragment key={p}>
          <span className={`px-2 py-0.5 rounded-full font-medium transition-all ${
            i < cur  ? "bg-green-100 text-green-700" :
            i === cur ? "bg-blue-600 text-white shadow-sm" :
                        "bg-gray-100 text-gray-400"
          }`}>{LABELS[p]}</span>
          {i < PHASES.length - 1 && (
            <span className={`text-xs ${i < cur ? "text-green-400" : "text-gray-200"}`}>›</span>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ─── Chat message renderer ──────────────────────────────────────────────────

function ChatMessage({ msg }) {
  if (msg.type === "status") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-100 text-blue-600 text-xs">
          <span className="pulse-dot w-1.5 h-1.5 rounded-full bg-blue-400 inline-block" />
          {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "milestone") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-50 border border-green-100 text-green-700 text-xs">
          <span>✓</span>{msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "error") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="px-3 py-1.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs max-w-xs text-center">
          ⚠ {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "user") {
    return (
      <div className="flex justify-end mb-3 msg-enter">
        <div className="max-w-[80%] bg-blue-600 text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }
  // agent
  return (
    <div className="flex justify-start mb-3 gap-2 msg-enter">
      <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold">
        AI
      </div>
      <div className="max-w-[80%] bg-white border border-gray-100 shadow-sm rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm leading-relaxed text-gray-800 whitespace-pre-wrap">
        {msg.content}
      </div>
    </div>
  );
}

// ─── Chat panel ──────────────────────────────────────────────────────────────

function ChatPanel({ messages, isWaitingAnswer, phase, onSend, isStarted }) {
  const [input, setInput] = useState("");
  const endRef    = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  // Auto-resize textarea
  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  const isProcessing = ["criteria", "retrieval", "scoring"].includes(phase) && !isWaitingAnswer;

  const placeholder = !isStarted
    ? "Describe your insurance needs to get started…"
    : isWaitingAnswer ? "Type your answer…"
    : isProcessing   ? "Processing…"
    : "Type a message…";

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isProcessing) return;
    onSend(input.trim());
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-16 h-16 rounded-2xl bg-blue-50 flex items-center justify-center text-3xl mb-4">🛡️</div>
            <h3 className="font-semibold text-gray-800 mb-1">AI Insurance Consultant</h3>
            <p className="text-gray-400 text-sm">Tell me about yourself and your insurance goals and I'll find the best match for you.</p>
          </div>
        )}
        {messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
        <div ref={endRef} />
      </div>

      {/* Input */}
      <div className="border-t border-gray-100 p-3 bg-white flex-shrink-0">
        <form onSubmit={handleSubmit} className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isProcessing}
            className="flex-1 px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-2xl text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent disabled:opacity-40 transition resize-none overflow-y-auto leading-relaxed"
            style={{ minHeight: "42px", maxHeight: "160px" }}
          />
          <button
            type="submit"
            disabled={isProcessing || !input.trim()}
            className="px-5 py-2.5 bg-blue-600 text-white rounded-2xl text-sm font-medium hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex-shrink-0"
          >
            {!isStarted ? "Start" : isWaitingAnswer ? "Reply" : "Send"}
          </button>
        </form>
        <p className="text-[10px] text-gray-300 mt-1.5 ml-1">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}

// ─── Requirements panel ──────────────────────────────────────────────────────

function SourceBadge({ source }) {
  const MAP = {
    "User input":        "bg-blue-50 text-blue-700 border-blue-100",
    "Recommended":       "bg-amber-50 text-amber-700 border-amber-100",
    "Inferred":          "bg-purple-50 text-purple-700 border-purple-100",
    "System calculated": "bg-gray-50 text-gray-500 border-gray-100",
  };
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded border font-medium ${MAP[source] || MAP["System calculated"]}`}>
      {source}
    </span>
  );
}

function RequirementItemCard({ item }) {
  const displayValue = Array.isArray(item.value)
    ? item.value.join(", ")
    : item.value === true ? "Yes"
    : item.value === false ? "No"
    : String(item.value ?? "—");

  return (
    <div className="bg-white rounded-xl p-3.5 border border-gray-100">
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <span className="text-[11px] text-gray-400 font-medium">{item.label}</span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {item.confirmed_by_user && (
            <span className="text-[10px] text-green-600 font-medium">✓ confirmed</span>
          )}
          <SourceBadge source={item.source} />
        </div>
      </div>
      <div className="text-sm font-semibold text-gray-900 leading-snug">{displayValue}</div>
      {item.reasoning && (
        <div className="text-[11px] text-gray-400 mt-1.5 italic leading-relaxed">{item.reasoning}</div>
      )}
    </div>
  );
}

function RequirementsView({ data }) {
  if (!data || !data.items || data.items.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 text-gray-400">
        <div className="text-4xl mb-3">👤</div>
        <p className="text-sm">Your profile will appear here once the consultation begins.</p>
      </div>
    );
  }

  // Group by source for a cleaner layout
  const userItems      = data.items.filter((i) => i.source === "User input");
  const inferredItems  = data.items.filter((i) => i.source === "Inferred" || i.source === "System calculated");
  const recommendedItems = data.items.filter((i) => i.source === "Recommended");

  const Section = ({ title, items }) => items.length === 0 ? null : (
    <div>
      <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-3">{title}</div>
      <div className="space-y-2">
        {items.map((item) => <RequirementItemCard key={item.key} item={item} />)}
      </div>
    </div>
  );

  return (
    <div className="p-5 space-y-6 overflow-y-auto h-full">
      <Section title="What you told us" items={userItems} />
      <Section title="Recommended" items={recommendedItems} />
      <Section title="Inferred" items={inferredItems} />
    </div>
  );
}

// ─── Criteria panel ──────────────────────────────────────────────────────────

function CriterionCard({ item }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-xl border border-gray-100 overflow-hidden">
      <button
        className="w-full p-3 text-left flex items-center gap-3 hover:bg-gray-50 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-sm font-medium text-gray-800 truncate">{item.item}</span>
            <span className="text-xs font-bold text-blue-600 ml-2 flex-shrink-0">{item.weight}%</span>
          </div>
          <div className="w-full bg-gray-100 rounded-full h-1.5">
            <div className="bg-blue-500 h-1.5 rounded-full transition-all" style={{ width: `${item.weight}%` }} />
          </div>
        </div>
        <span className="text-gray-300 text-xs flex-shrink-0">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="px-3 pb-3 pt-2 border-t border-gray-50 space-y-2 expand-enter">
          <div>
            <div className="text-[10px] uppercase font-semibold text-gray-300 mb-1">What to look for</div>
            <p className="text-xs text-gray-600 leading-relaxed">{item.description}</p>
          </div>
          <div>
            <div className="text-[10px] uppercase font-semibold text-gray-300 mb-1">Scoring rules</div>
            <p className="text-xs text-gray-600 leading-relaxed">{item.scoring_rules}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function CriteriaView({ data }) {
  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 text-gray-400">
        <div className="text-4xl mb-3">📋</div>
        <p className="text-sm">Scoring criteria will appear once your profile is complete.</p>
      </div>
    );
  }

  const sorted = [...(data.criteria || [])].sort((a, b) => b.weight - a.weight);
  const total  = (data.criteria || []).reduce((s, c) => s + c.weight, 0);

  return (
    <div className="p-5 space-y-5 overflow-y-auto h-full">
      {data.filters && data.filters.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Hard Filters &mdash; must pass all
          </div>
          <div className="space-y-2">
            {data.filters.map((f, i) => (
              <div key={i} className="flex items-start gap-2 bg-white rounded-xl p-3 border border-gray-100">
                <span className="text-red-400 flex-shrink-0 mt-0.5 text-xs">●</span>
                <span className="text-sm text-gray-700">{f}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {sorted.length > 0 && (
        <div>
          <div className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide mb-3">
            Weighted Criteria — total {total}%
          </div>
          <div className="space-y-3">
            {sorted.map((item, i) => <CriterionCard key={i} item={item} />)}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Policies panel ──────────────────────────────────────────────────────────

function ScoreDigit({ score }) {
  const color = score >= 4 ? "text-green-600" : score >= 3 ? "text-amber-500" : "text-red-500";
  return (
    <span className={`text-2xl font-extrabold tabular-nums leading-none ${color}`}>
      {score}
      <span className="text-sm font-normal text-gray-300">/5</span>
    </span>
  );
}

function PolicyCard({ policy, rank }) {
  const [showFilters, setShowFilters] = useState(true);
  const [showScores,  setShowScores]  = useState(rank === 1);
  const [showCtx,     setShowCtx]     = useState(false);

  const passes     = policy.fulfil_filters[0];
  const filterNote = policy.fulfil_filters[1];
  const totalScore = policy.scoring.reduce(
    (s, [score, crit]) => s + score * (crit.weight / 100), 0
  );

  const totalColor = totalScore >= 4 ? "text-green-600" : totalScore >= 3 ? "text-amber-500" : "text-red-500";

  const filterEvidence = policy.retrieved_context?.filters || [];
  const criteriaEvidence = policy.retrieved_context?.criteria || [];

  return (
    <div className={`bg-white rounded-xl border overflow-hidden ${
      rank === 1 && passes ? "border-blue-200 shadow-md" : "border-gray-100"
    }`}>
      {/* Header */}
      <div className="p-4 flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            {rank === 1 && passes && (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-600 text-white font-semibold tracking-wide">
                TOP PICK
              </span>
            )}
            {passes ? (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-50 text-green-700 border border-green-100 font-medium">
                ✓ All filters passed
              </span>
            ) : (
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-red-50 text-red-700 border border-red-100 font-medium">
                ✗ Filtered out
              </span>
            )}
          </div>
          <span className="font-semibold text-gray-900">{policy.policy_name}</span>
        </div>
        {/* Overall score — large digits, no bar */}
        <div className="text-right flex-shrink-0">
          <div className="text-[10px] text-gray-400 mb-0.5">Overall</div>
          <span className={`text-3xl font-extrabold tabular-nums leading-none ${totalColor}`}>
            {totalScore.toFixed(1)}
            <span className="text-sm font-normal text-gray-300">/5</span>
          </span>
        </div>
      </div>

      {/* Hard filter evaluation */}
      <div className="border-t border-gray-50">
        <button
          className="w-full px-4 py-2.5 text-left text-xs font-semibold text-gray-500 flex justify-between items-center hover:bg-gray-50 transition-colors"
          onClick={() => setShowFilters(!showFilters)}
        >
          <span className="flex items-center gap-1.5">
            <span className={passes ? "text-green-500" : "text-red-400"}>■</span>
            Hard Filter Evaluation
          </span>
          <span className="text-gray-300">{showFilters ? "▲" : "▼"}</span>
        </button>
        {showFilters && (
          <div className="px-4 pb-4 space-y-3 expand-enter">
            {/* Overall filter verdict */}
            {filterNote && (
              <div className={`rounded-lg p-3 text-sm leading-relaxed ${
                passes
                  ? "bg-green-50 text-green-800 border border-green-100"
                  : "bg-red-50 text-red-800 border border-red-100"
              }`}>
                <div className="text-[10px] uppercase font-semibold mb-1 opacity-60">Verdict</div>
                {filterNote}
              </div>
            )}
            {/* Per-filter evidence */}
            {filterEvidence.length > 0 && (
              <div className="space-y-2">
                <div className="text-[10px] uppercase font-semibold text-gray-300">Filter Evidence</div>
                {filterEvidence.map((ctx, j) => (
                  <div key={j} className="bg-slate-50 border border-gray-100 rounded-lg p-3 text-xs text-gray-600 leading-relaxed">
                    {ctx}
                  </div>
                ))}
              </div>
            )}
            {filterEvidence.length === 0 && !filterNote && (
              <p className="text-xs text-gray-400 italic">No filter evidence retrieved.</p>
            )}
          </div>
        )}
      </div>

      {/* Criteria scores */}
      <div className="border-t border-gray-50">
        <button
          className="w-full px-4 py-2.5 text-left text-xs font-semibold text-gray-500 flex justify-between items-center hover:bg-gray-50 transition-colors"
          onClick={() => setShowScores(!showScores)}
        >
          <span className="flex items-center gap-1.5">
            <span className="text-blue-400">■</span>
            Criterion Scores
          </span>
          <span className="text-gray-300">{showScores ? "▲" : "▼"}</span>
        </button>
        {showScores && (
          <div className="px-4 pb-4 space-y-4 expand-enter">
            {policy.scoring.map(([score, crit, reason], j) => (
              <div key={j} className="flex gap-3">
                {/* Score digit column */}
                <div className="flex-shrink-0 w-14 flex flex-col items-center justify-start pt-0.5">
                  <ScoreDigit score={score} />
                  <span className="text-[10px] text-gray-300 mt-0.5">w: {crit.weight}%</span>
                </div>
                {/* Label + reason */}
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-semibold text-gray-800 mb-1">{crit.item}</div>
                  <p className="text-xs text-gray-500 leading-relaxed">{reason}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Source evidence */}
      {criteriaEvidence.length > 0 && (
        <div className="border-t border-gray-50">
          <button
            className="w-full px-4 py-2.5 text-left text-xs font-semibold text-gray-500 flex justify-between items-center hover:bg-gray-50 transition-colors"
            onClick={() => setShowCtx(!showCtx)}
          >
            <span className="flex items-center gap-1.5">
              <span className="text-purple-400">■</span>
              Criteria Evidence ({criteriaEvidence.length})
            </span>
            <span className="text-gray-300">{showCtx ? "▲" : "▼"}</span>
          </button>
          {showCtx && (
            <div className="px-4 pb-4 space-y-2 expand-enter">
              {criteriaEvidence.map((ctx, j) => (
                <div key={j} className="text-[11px] font-mono text-gray-600 bg-slate-50 rounded-lg p-3 border border-gray-100 leading-relaxed">
                  {ctx}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PoliciesView({ data }) {
  if (!data || data.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full text-center px-6 text-gray-400">
        <div className="text-4xl mb-3">📊</div>
        <p className="text-sm">Policy evaluations will appear once the analysis is complete.</p>
      </div>
    );
  }

  const ranked = data
    .map((p) => {
      const score = p.scoring.reduce(
        (s, [sc, crit]) => s + sc * (crit.weight / 100), 0
      );
      return { ...p, _score: score };
    })
    .sort((a, b) => {
      if (a.fulfil_filters[0] !== b.fulfil_filters[0])
        return b.fulfil_filters[0] - a.fulfil_filters[0];
      return b._score - a._score;
    });

  const passing = ranked.filter((p) => p.fulfil_filters[0]).length;

  return (
    <div className="p-5 space-y-4 overflow-y-auto h-full">
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>{data.length} policies evaluated — {passing} passed all filters</span>
        <span>Sorted by weighted score</span>
      </div>
      {ranked.map((p, i) => (
        <PolicyCard key={i} policy={p} rank={i + 1} />
      ))}
    </div>
  );
}

// ─── Data panel (tabs) ───────────────────────────────────────────────────────

function DataPanel({ requirements, criteria, policies, activeTab, setActiveTab }) {
  const TABS = [
    { id: "requirements", label: "Requirements", icon: "👤", hasData: !!requirements },
    { id: "criteria",     label: "Criteria",     icon: "📋", hasData: !!criteria },
    { id: "policies",     label: "Policies",     icon: "📊", hasData: policies && policies.length > 0 },
  ];

  return (
    <div className="flex flex-col h-full bg-slate-50">
      {/* Tab bar */}
      <div className="bg-white border-b border-gray-100 px-4 pt-3 flex-shrink-0">
        <div className="flex gap-1">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`relative px-4 py-2 text-sm font-medium rounded-t-lg transition-colors flex items-center gap-1.5 ${
                activeTab === tab.id
                  ? "bg-slate-50 text-blue-600 border-b-2 border-blue-600 -mb-px"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              <span>{tab.icon}</span>
              {tab.label}
              {tab.hasData && (
                <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  activeTab === tab.id ? "bg-blue-400" : "bg-green-400"
                }`} />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-hidden">
        {activeTab === "requirements" && <RequirementsView data={requirements} />}
        {activeTab === "criteria"     && <CriteriaView    data={criteria} />}
        {activeTab === "policies"     && <PoliciesView    data={policies} />}
      </div>
    </div>
  );
}

// ─── Root App ────────────────────────────────────────────────────────────────

function App() {
  const [sessionId,       setSessionId]       = useState(null);
  const [messages,        setMessages]        = useState([]);
  const [phase,           setPhase]           = useState("idle");
  const [isWaiting,       setIsWaiting]       = useState(false);
  const [requirements,    setRequirements]    = useState(null);
  const [criteria,        setCriteria]        = useState(null);
  const [policies,        setPolicies]        = useState([]);
  const [activeTab,       setActiveTab]       = useState("requirements");
  const wsRef             = useRef(null);
  const sessionIdRef      = useRef(null);

  const addMsg = useCallback((type, content) => {
    setMessages((prev) => [...prev, mkMsg(type, content)]);
  }, []);

  // WebSocket message dispatcher
  const handleWsMsg = useCallback((raw) => {
    const d = JSON.parse(raw);
    switch (d.type) {
      case "question":
        addMsg("agent", d.content);
        setIsWaiting(true);
        break;
      case "status":
        if (d.phase) setPhase(d.phase);
        addMsg("status", d.message);
        break;
      case "requirements":
        setRequirements(d.data);
        setActiveTab("requirements");
        addMsg("milestone", "Profile captured successfully");
        break;
      case "criteria":
        setCriteria(d.data);
        setActiveTab("criteria");
        addMsg("milestone", `${d.data.criteria?.length ?? 0} scoring criteria generated`);
        break;
      case "policies":
        setPolicies(d.data);
        setActiveTab("policies");
        addMsg("milestone", `${d.data.length} policies evaluated`);
        break;
      case "complete":
        setPhase("complete");
        addMsg("milestone", d.message || "Analysis complete!");
        break;
      case "error":
        addMsg("error", d.message);
        break;
      case "ping":
        break; // heartbeat, ignore
      default:
        break;
    }
  }, [addMsg]);

  const handleSend = useCallback(async (text) => {
    addMsg("user", text);

    if (!sessionIdRef.current) {
      // First message — create session + open WebSocket
      try {
        const resp = await fetch("/api/sessions", { method: "POST" });
        const { session_id } = await resp.json();
        sessionIdRef.current = session_id;
        setSessionId(session_id);

        const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
        const ws = new WebSocket(`${proto}//${window.location.host}/ws/${session_id}`);
        wsRef.current = ws;

        ws.onopen    = () => ws.send(JSON.stringify({ type: "start", message: text }));
        ws.onmessage = (e) => handleWsMsg(e.data);
        ws.onerror   = () => addMsg("error", "Connection error. Please refresh.");
      } catch {
        addMsg("error", "Failed to connect to the API server.");
      }
    } else {
      // Subsequent message — answer to agent question
      setIsWaiting(false);
      wsRef.current?.send(JSON.stringify({ type: "answer", content: text }));
    }
  }, [addMsg, handleWsMsg]);

  const handleReset = useCallback(() => {
    wsRef.current?.close();
    wsRef.current      = null;
    sessionIdRef.current = null;
    setSessionId(null);
    setMessages([]);
    setPhase("idle");
    setIsWaiting(false);
    setRequirements(null);
    setCriteria(null);
    setPolicies([]);
    setActiveTab("requirements");
  }, []);

  const isStarted = !!sessionId || messages.length > 0;

  return (
    <div className="flex flex-col h-screen">
      {/* Global header */}
      <header className="bg-white border-b border-gray-100 px-5 py-3 flex items-center justify-between flex-shrink-0 shadow-sm">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-blue-600 flex items-center justify-center text-white">🛡️</div>
          <div>
            <h1 className="text-sm font-bold text-gray-900 leading-tight">AI Insurance Consultant</h1>
            <p className="text-[11px] text-gray-400">GPT-4o · LangGraph · RAG</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          {phase !== "idle" && <PhaseBar phase={phase} />}
          {isStarted && (
            <button
              onClick={handleReset}
              className="text-xs px-3 py-1.5 rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
            >
              New session
            </button>
          )}
        </div>
      </header>

      {/* Body */}
      <div className="flex flex-1 overflow-hidden">
        {/* Left — chat */}
        <div className="w-1/2 flex-shrink-0 border-r border-gray-100 bg-white flex flex-col">
          <ChatPanel
            messages={messages}
            isWaitingAnswer={isWaiting}
            phase={phase}
            onSend={handleSend}
            isStarted={isStarted}
          />
        </div>

        {/* Right — data panels */}
        <div className="flex-1 overflow-hidden">
          <DataPanel
            requirements={requirements}
            criteria={criteria}
            policies={policies}
            activeTab={activeTab}
            setActiveTab={setActiveTab}
          />
        </div>
      </div>
    </div>
  );
}

// Mount
const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
