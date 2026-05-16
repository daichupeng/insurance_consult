/* global React, ReactDOM */
const { useState, useEffect, useRef, useCallback } = React;

// ─── Helpers ────────────────────────────────────────────────────────────────

let _msgId = 0;
function mkMsg(type, content, statusPhase) {
  return { id: String(++_msgId), type, content, statusPhase };
}

function MarkdownContent({ content }) {
  if (!content) return null;
  let html = content;
  if (typeof marked !== 'undefined') {
    try {
      const opts = { breaks: true, gfm: true, mangle: false, headerIds: false };
      html = typeof marked.parse === 'function' ? marked.parse(content, opts) : marked(content, opts);
    } catch (e) { html = content.replace(/\n/g, '<br/>'); }
  } else {
    html = content.replace(/\n/g, '<br/>');
  }
  return <div className="markdown-content" dangerouslySetInnerHTML={{ __html: html }} />;
}

// ─── Shared UI Atoms ─────────────────────────────────────────────────────────

function IconButton({ onClick, title, children, className = "" }) {
  return (
    <button
      onClick={onClick}
      title={title}
      className={`w-8 h-8 rounded-full bg-[#f5f5f7] text-[#6e6e73] hover:bg-[#e5e5ea] hover:text-[#1d1d1f] flex items-center justify-center transition-colors text-sm ${className}`}
    >
      {children}
    </button>
  );
}

function Tag({ children, color = "gray" }) {
  const map = {
    gray:   "bg-[#f5f5f7] text-[#6e6e73] border-[#e5e5ea]",
    blue:   "bg-[#e8f2ff] text-[#0071e3] border-[#c2deff]",
    green:  "bg-[#f0fdf4] text-[#15803d] border-[#bbf7d0]",
    amber:  "bg-[#fffbeb] text-[#b45309] border-[#fde68a]",
    red:    "bg-[#fff1f2] text-[#e11d48] border-[#fecdd3]",
    purple: "bg-[#faf5ff] text-[#7c3aed] border-[#e9d5ff]",
  };
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-medium border ${map[color]}`}>
      {children}
    </span>
  );
}

function SectionLabel({ children }) {
  return (
    <div className="text-[10px] font-semibold text-[#86868b] uppercase tracking-[0.08em] mb-3">
      {children}
    </div>
  );
}

// ─── Phase Bar ───────────────────────────────────────────────────────────────

function PhaseBar({ phase }) {
  const PHASES = ["profile", "criteria", "fetching", "retrieval", "scoring", "complete"];
  const LABELS = { profile: "Profile", criteria: "Criteria", fetching: "Fetching", retrieval: "Retrieval", scoring: "Scoring", complete: "Complete" };
  const cur = PHASES.indexOf(phase);
  return (
    <div className="flex items-center gap-1 text-[11px]">
      {PHASES.map((p, i) => (
        <React.Fragment key={p}>
          <span className={`px-2.5 py-1 rounded-full font-medium transition-all ${
            i < cur  ? "bg-[#f0fdf4] text-[#15803d]" :
            i === cur ? "bg-[#0071e3] text-white" :
                        "bg-[#f5f5f7] text-[#86868b]"
          }`}>{LABELS[p]}</span>
          {i < PHASES.length - 1 && (
            <span className={i < cur ? "text-[#86c96e]" : "text-[#d2d2d7]"}>›</span>
          )}
        </React.Fragment>
      ))}
    </div>
  );
}

// ─── Chat Components ─────────────────────────────────────────────────────────

function TypingBubble() {
  return (
    <div className="flex justify-start mb-3 gap-2 msg-enter">
      <div className="bg-[#f5f5f7] rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
        <span className="w-1.5 h-1.5 bg-[#86868b] rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-1.5 h-1.5 bg-[#86868b] rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="w-1.5 h-1.5 bg-[#86868b] rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}

function ChatMessage({ msg }) {
  if (msg.type === "status") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#e8f2ff] text-[#0071e3] text-[10px] font-medium">
          <span className="pulse-dot w-1.5 h-1.5 rounded-full bg-[#0071e3] inline-block" />
          {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "milestone") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-[#f0fdf4] text-[#15803d] text-[10px] font-medium border border-[#bbf7d0]">
          <svg width="10" height="10" viewBox="0 0 10 10" fill="none"><path d="M2 5l2 2 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
          {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "error") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="px-3 py-1.5 rounded-xl bg-[#fff1f2] border border-[#fecdd3] text-[#e11d48] text-xs max-w-xs text-center font-medium">
          {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "user") {
    return (
      <div className="flex justify-end mb-3 msg-enter">
        <div className="max-w-[78%] bg-[#0071e3] text-white rounded-2xl rounded-br-sm px-4 py-2.5 text-sm leading-relaxed">
          {msg.content}
        </div>
      </div>
    );
  }
  return (
    <div className="flex justify-start mb-3 gap-2 msg-enter">
      <div className="max-w-[82%] bg-[#f5f5f7] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm leading-relaxed text-[#1d1d1f]">
        <MarkdownContent content={msg.content} />
      </div>
    </div>
  );
}

function ChatPanel({ messages, isWaitingAnswer, isTyping, phase, onSend, isStarted }) {
  const [input, setInput] = useState("");
  const endRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, isTyping]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 140) + "px";
  }, [input]);

  const isProcessing = ["criteria", "fetching", "retrieval", "scoring"].includes(phase) && !isWaitingAnswer;
  const placeholder = !isStarted ? "How can I help you today?"
    : isWaitingAnswer ? "Type your answer…"
    : isProcessing ? "Thinking…"
    : "Message…";

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!input.trim() || isProcessing) return;
    onSend(input.trim());
    setInput("");
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSubmit(e); }
  };

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-white">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-5">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6 py-12">
            <div className="w-14 h-14 rounded-2xl bg-[#e8f2ff] flex items-center justify-center text-2xl mb-4">🛡️</div>
            <h3 className="text-base font-semibold text-[#1d1d1f] mb-1.5 tracking-tight">AI Insurance Advisor</h3>
            <p className="text-[#6e6e73] text-sm max-w-[240px] leading-relaxed">Here to help you find the best coverage for your needs.</p>
          </div>
        )}
        {messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
        {isTyping && <TypingBubble />}
        <div ref={endRef} />
      </div>

      {/* Input bar */}
      <div className="flex-shrink-0 px-4 py-3 border-t border-[#e5e5ea] bg-white">
        <form onSubmit={handleSubmit} className="flex items-end gap-2 bg-[#f5f5f7] rounded-2xl px-3 py-2 border border-[#e5e5ea] focus-within:border-[#0071e3] focus-within:bg-white transition-all">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isProcessing}
            className="flex-1 bg-transparent text-sm text-[#1d1d1f] focus:outline-none disabled:opacity-40 resize-none leading-relaxed placeholder:text-[#86868b]"
            style={{ minHeight: "24px", maxHeight: "140px" }}
          />
          <button
            type="submit"
            disabled={isProcessing || !input.trim()}
            className="w-8 h-8 bg-[#0071e3] text-white rounded-full flex items-center justify-center hover:bg-[#0077ed] disabled:opacity-30 disabled:cursor-not-allowed transition-colors flex-shrink-0 mb-0.5"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/>
            </svg>
          </button>
        </form>
        <p className="text-[10px] text-[#86868b] mt-1.5 ml-1">Return to send · Shift+Return for new line</p>
      </div>
    </div>
  );
}

// ─── Requirements View ───────────────────────────────────────────────────────

function RequirementItemCard({ item }) {
  const displayValue = Array.isArray(item.value)
    ? item.value.join(", ")
    : item.value === true ? "Yes"
    : item.value === false ? "No"
    : String(item.value ?? "—");

  return (
    <div className="bg-white rounded-xl p-4 border border-[#e5e5ea] hover:border-[#d2d2d7] transition-colors">
      <div className="flex items-start justify-between gap-2 mb-2">
        <span className="text-[10px] font-semibold text-[#86868b] uppercase tracking-[0.07em]">{item.label}</span>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {item.confirmed_by_user && <Tag color="green">Confirmed</Tag>}
          <Tag>{item.source}</Tag>
        </div>
      </div>
      <div className="text-sm font-medium text-[#1d1d1f]">{displayValue}</div>
      {item.reasoning && (
        <div className="text-[12px] text-[#6e6e73] mt-2 pt-2 border-t border-[#f5f5f7] leading-relaxed">{item.reasoning}</div>
      )}
    </div>
  );
}

function RequirementsView({ data }) {
  if (!data?.items?.length) return (
    <div className="h-full flex flex-col items-center justify-center text-[#86868b] p-8">
      <div className="text-4xl mb-3 opacity-40">👤</div>
      <p className="text-sm text-[#6e6e73]">Building profile…</p>
    </div>
  );
  return (
    <div className="p-5 space-y-3 overflow-y-auto h-full bg-[#f5f5f7]">
      {data.items.map(item => <RequirementItemCard key={item.key} item={item} />)}
    </div>
  );
}

// ─── Criteria View ───────────────────────────────────────────────────────────

function CriterionCard({ item }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-xl border border-[#e5e5ea] overflow-hidden">
      <button className="w-full px-4 py-3.5 text-left flex items-center gap-3 hover:bg-[#f5f5f7] transition-colors" onClick={() => setOpen(!open)}>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[#1d1d1f] truncate">{item.item}</span>
            <span className="text-[11px] font-semibold text-[#0071e3] bg-[#e8f2ff] px-2 py-0.5 rounded-full ml-2 flex-shrink-0">{item.weight}%</span>
          </div>
          <div className="w-full bg-[#f5f5f7] rounded-full h-1.5">
            <div className="bg-[#0071e3] h-full rounded-full transition-all duration-500" style={{ width: `${item.weight}%` }} />
          </div>
        </div>
        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" className={`text-[#86868b] transition-transform duration-200 flex-shrink-0 ${open ? 'rotate-180' : ''}`}>
          <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </button>
      {open && (
        <div className="px-4 pb-4 pt-2 border-t border-[#f5f5f7] space-y-3 bg-[#f5f5f7]">
          <div>
            <SectionLabel>Objective</SectionLabel>
            <p className="text-xs text-[#1d1d1f] leading-relaxed">{item.description}</p>
          </div>
          <div className="bg-white rounded-lg p-3 border border-[#e5e5ea]">
            <SectionLabel>Scoring Criteria</SectionLabel>
            <p className="text-xs text-[#1d1d1f] leading-relaxed">{item.scoring_rules}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function CriteriaView({ data }) {
  if (!data?.criteria?.length && !data?.filters?.length) return (
    <div className="h-full flex flex-col items-center justify-center text-[#86868b] p-8">
      <div className="text-4xl mb-3 opacity-40">📋</div>
      <p className="text-sm text-[#6e6e73]">Waiting for profile completion…</p>
    </div>
  );
  return (
    <div className="p-5 space-y-5 overflow-y-auto h-full bg-[#f5f5f7]">
      {data.filters?.length > 0 && (
        <div>
          <SectionLabel>Mandatory Filters</SectionLabel>
          <div className="grid grid-cols-1 gap-2">
            {data.filters.map((f, i) => (
              <div key={i} className="flex items-center gap-2.5 bg-white px-4 py-2.5 rounded-xl border border-[#e5e5ea]">
                <div className="w-1.5 h-1.5 rounded-full bg-[#0071e3] flex-shrink-0" />
                <span className="text-sm text-[#1d1d1f]">{f}</span>
              </div>
            ))}
          </div>
        </div>
      )}
      <div>
        <SectionLabel>Weighted Scoring</SectionLabel>
        <div className="space-y-2">
          {data.criteria.map((c, i) => <CriterionCard key={i} item={c} />)}
        </div>
      </div>
    </div>
  );
}

// ─── Policies View ───────────────────────────────────────────────────────────

function PolicyRankEntry({ policy, rank }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const totalScore = policy.scoring.reduce((s, [sc, crit]) => s + sc * (crit.weight / 100), 0);
  const scoreColor = totalScore >= 4 ? "text-[#15803d]" : totalScore >= 3 ? "text-[#b45309]" : "text-[#e11d48]";

  return (
    <div className={`bg-white rounded-2xl border transition-all duration-300 mb-4 ${isExpanded ? 'border-[#0071e3]/30 shadow-sm' : 'border-[#e5e5ea] hover:border-[#d2d2d7]'}`}>
      <div className="p-5">
        <div className="flex items-start justify-between gap-4 mb-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <span className="w-7 h-7 rounded-lg bg-[#1d1d1f] text-white text-xs font-semibold flex items-center justify-center flex-shrink-0">{rank}</span>
              <Tag color={policy.fulfil_filters[0] ? "green" : "red"}>
                {policy.fulfil_filters[0] ? "Eligible" : "Ineligible"}
              </Tag>
            </div>
            <h4 className="font-semibold text-[#1d1d1f] text-base leading-snug tracking-tight">{policy.policy_name}</h4>
            {!policy.fulfil_filters[0] && (
              <p className="text-xs text-[#e11d48] mt-1 leading-relaxed">{policy.fulfil_filters[1]}</p>
            )}
          </div>
          <div className="text-right flex-shrink-0">
            <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-0.5">Match</div>
            <div className={`text-3xl font-semibold tabular-nums ${scoreColor}`}>{totalScore.toFixed(1)}</div>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-4 py-4 border-y border-[#f5f5f7]">
          <div>
            <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-1">Premium</div>
            <div className="text-sm font-semibold text-[#1d1d1f]">{policy.basic_info.annual_premium}</div>
          </div>
          <div>
            <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-1">Return Rate</div>
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-[#1d1d1f]">{(policy.return_rate * 100).toFixed(2)}%</span>
              <div className="flex gap-1">
                {policy.basic_info.product_summary_url && (
                  <a href={policy.basic_info.product_summary_url} target="_blank"
                    className="w-6 h-6 rounded-full bg-[#f5f5f7] text-[#6e6e73] flex items-center justify-center text-[10px] hover:bg-[#e8f2ff] hover:text-[#0071e3] transition-colors"
                    title="Product Summary">📄</a>
                )}
                {policy.basic_info.brochure_url && (
                  <a href={policy.basic_info.brochure_url} target="_blank"
                    className="w-6 h-6 rounded-full bg-[#f5f5f7] text-[#6e6e73] flex items-center justify-center text-[10px] hover:bg-[#f5f0ff] hover:text-[#7c3aed] transition-colors"
                    title="Brochure">📖</a>
                )}
              </div>
            </div>
          </div>
        </div>

        {isExpanded && (
          <div className="mt-4 space-y-5">
            <div>
              <SectionLabel>Score Breakdown</SectionLabel>
              <div className="space-y-2">
                {policy.scoring.map(([score, crit, reasoning], i) => (
                  <div key={i} className="p-3 bg-[#f5f5f7] rounded-xl">
                    <div className="flex justify-between items-center mb-1.5">
                      <span className="text-sm font-medium text-[#1d1d1f]">{crit.item}</span>
                      <span className={`text-sm font-semibold ${score >= 4 ? 'text-[#15803d]' : score >= 3 ? 'text-[#b45309]' : 'text-[#e11d48]'}`}>{score}/5</span>
                    </div>
                    <p className="text-xs text-[#6e6e73] leading-relaxed">{reasoning}</p>
                  </div>
                ))}
              </div>
            </div>

            {(policy.context_summary && Object.keys(policy.context_summary).length > 0) && (
              <div>
                <SectionLabel>Deep Dive</SectionLabel>
                <div className="space-y-3">
                  {Object.entries(policy.context_summary).map(([title, text], i) => (
                    <div key={i} className="pl-3 border-l-2 border-[#e5e5ea]">
                      <h5 className="text-xs font-semibold text-[#1d1d1f] mb-1.5">{title}</h5>
                      <MarkdownContent content={text} />
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className={`w-full mt-4 py-2.5 rounded-xl text-xs font-medium transition-all flex items-center justify-center gap-2 ${
            isExpanded
              ? 'bg-[#1d1d1f] text-white'
              : 'bg-[#f5f5f7] text-[#6e6e73] hover:bg-[#e8f2ff] hover:text-[#0071e3]'
          }`}
        >
          {isExpanded ? 'Collapse' : 'View Details'}
          <svg width="11" height="11" viewBox="0 0 11 11" fill="none" className={`transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''}`}>
            <path d="M1.5 3.5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
        </button>
      </div>
    </div>
  );
}

function PoliciesView({ data }) {
  if (!data?.length) return (
    <div className="h-full flex flex-col items-center justify-center text-[#86868b] p-8">
      <div className="text-4xl mb-3 opacity-40">📊</div>
      <p className="text-sm text-[#6e6e73]">Analyzing options…</p>
    </div>
  );
  return (
    <div className="p-5 overflow-y-auto h-full bg-[#f5f5f7]">
      {data.map((p, i) => <PolicyRankEntry key={i} policy={p} rank={i + 1} />)}
    </div>
  );
}

// ─── Claiming Panel ───────────────────────────────────────────────────────────

function ClaimingPanel({ data }) {
  const [tab, setTab] = useState("summary");

  if (!data) return (
    <div className="h-full flex flex-col items-center justify-center p-8 text-[#86868b]">
      <div className="w-12 h-12 bg-white rounded-xl flex items-center justify-center text-xl mb-4 border border-[#e5e5ea]">📝</div>
      <p className="text-sm text-[#6e6e73]">Awaiting claim details…</p>
    </div>
  );

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-[#f5f5f7]">
      <div className="bg-white border-b border-[#e5e5ea] flex px-5 pt-4">
        {['summary', 'policies'].map(t => (
          <button
            key={t} onClick={() => setTab(t)}
            className={`px-3 pb-3 text-xs font-medium transition-all mr-4 border-b-2 ${tab === t ? 'text-[#0071e3] border-[#0071e3]' : 'text-[#86868b] border-transparent hover:text-[#6e6e73]'}`}
          >
            {t === 'summary' ? 'Summary' : 'Policies'}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {tab === 'summary' && (
          <div className="max-w-xl mx-auto space-y-4 pb-8">
            <div className="bg-white p-5 rounded-xl border border-[#e5e5ea]">
              <SectionLabel>Extracted Details</SectionLabel>
              <div className="flex flex-wrap gap-2">
                {Object.entries(data.details || {}).filter(([k]) => k !== 'possible_diagnoses').map(([k, v]) => (
                  <div key={k} className="bg-[#f5f5f7] px-3 py-1.5 rounded-lg flex flex-col gap-0.5">
                    <span className="text-[9px] uppercase tracking-wider text-[#86868b] font-medium">{k.replace(/_/g, " ")}</span>
                    <span className="text-sm font-medium text-[#1d1d1f]">{typeof v === 'string' ? v : JSON.stringify(v)}</span>
                  </div>
                ))}
                {(!data.details || Object.keys(data.details).filter(k => k !== 'possible_diagnoses').length === 0) && (
                  <span className="text-xs text-[#86868b]">No details extracted yet</span>
                )}
              </div>
            </div>

            <div className="bg-white p-5 rounded-xl border border-[#e5e5ea]">
              <SectionLabel>Diagnosis</SectionLabel>
              <div className="space-y-2">
                {(data.details?.possible_diagnoses || []).map((diag, idx) => {
                  const sObj = (data.treatment_strategies || []).find(s => {
                    const d = typeof s.diagnosis === 'object' ? s.diagnosis.diagnosis : s.diagnosis;
                    return d === diag;
                  });
                  return (
                    <details key={idx} className="bg-[#f5f5f7] rounded-xl overflow-hidden group">
                      <summary className="px-4 py-3 text-sm font-medium text-[#1d1d1f] cursor-pointer select-none hover:bg-[#ebebeb] flex items-center justify-between list-none">
                        <div className="flex items-center gap-2.5">
                          <span className="w-5 h-5 rounded-full bg-[#e8f2ff] text-[#0071e3] flex items-center justify-center text-[10px] font-semibold">{idx + 1}</span>
                          {diag}
                        </div>
                        <svg width="11" height="11" viewBox="0 0 11 11" fill="none" className="text-[#86868b] transition-transform group-open:rotate-180">
                          <path d="M1.5 3.5l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                        </svg>
                      </summary>
                      <div className="px-4 pb-4 pt-2 border-t border-[#e5e5ea] bg-white space-y-4">
                        <div>
                          <SectionLabel>Claiming Strategy</SectionLabel>
                          <MarkdownContent content={sObj?.claim_strategy || "No strategy generated"} />
                        </div>
                        {(sObj?.estimated_future_costs || []).length > 0 && (
                          <div>
                            <SectionLabel>Estimated Future Costs</SectionLabel>
                            <div className="space-y-1.5">
                              {sObj.estimated_future_costs.map((c, ci) => (
                                <div key={ci} className="flex justify-between items-start p-2.5 bg-[#f5f5f7] rounded-lg">
                                  <div>
                                    <span className="text-xs font-medium text-[#1d1d1f]">{c.item_name}</span>
                                    <div className="text-[10px] text-[#86868b] mt-0.5 uppercase tracking-wider">{c.relevant_insurance_type}</div>
                                  </div>
                                  <span className="text-xs font-semibold text-[#0071e3] bg-white px-2.5 py-1 rounded-lg border border-[#e5e5ea]">{c.item_cost}</span>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    </details>
                  );
                })}
                {(!data.details?.possible_diagnoses || data.details.possible_diagnoses.length === 0) && (
                  <p className="text-xs text-[#86868b]">No diagnosis available yet</p>
                )}
              </div>
            </div>
          </div>
        )}

        {tab === 'policies' && (
          <div className="max-w-xl mx-auto space-y-3 pb-8">
            {(data.policies || []).map((p, idx) => (
              <div key={idx} className="bg-white p-5 rounded-xl border border-[#e5e5ea]">
                <div className="flex items-center justify-between mb-3">
                  <div>
                    <h3 className="text-sm font-semibold text-[#1d1d1f]">{p.insurance_name}</h3>
                    <span className="text-[11px] text-[#86868b] uppercase tracking-wider">{p.category}{p.medical_type ? ` · ${p.medical_type}` : ''}</span>
                  </div>
                  <a href={`/raw_policies/uploaded/${p.insurance_name}.pdf`} target="_blank"
                    className="w-8 h-8 bg-[#f5f5f7] rounded-lg flex items-center justify-center text-[#6e6e73] hover:text-[#0071e3] hover:bg-[#e8f2ff] transition-colors"
                    title="View Document">📄</a>
                </div>
                {p.retrieved_contexts?.length > 0 && (
                  <details className="bg-[#f5f5f7] rounded-lg overflow-hidden">
                    <summary className="px-3 py-2 text-[11px] font-medium text-[#6e6e73] cursor-pointer hover:text-[#0071e3] select-none">
                      Extracted Clauses
                    </summary>
                    <div className="px-3 pb-3 pt-2 text-xs text-[#6e6e73] leading-relaxed border-t border-[#e5e5ea]">
                      <MarkdownContent content={p.retrieved_contexts[p.retrieved_contexts.length - 1]} />
                    </div>
                  </details>
                )}
              </div>
            ))}
            {(!data.policies || data.policies.length === 0) && (
              <div className="text-center py-8">
                <p className="text-sm text-[#86868b]">No matching active policies found.</p>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Modals ───────────────────────────────────────────────────────────────────

function ModalShell({ title, onClose, children }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#1d1d1f]/50 backdrop-blur-sm">
      <div className="bg-white rounded-2xl w-full max-w-md shadow-xl border border-[#e5e5ea] overflow-hidden">
        <div className="px-6 py-4 border-b border-[#e5e5ea] flex items-center justify-between">
          <h3 className="font-semibold text-[#1d1d1f]">{title}</h3>
          <button onClick={onClose} className="w-7 h-7 rounded-full hover:bg-[#f5f5f7] text-[#6e6e73] text-xl leading-none flex items-center justify-center transition-colors">&times;</button>
        </div>
        {children}
      </div>
    </div>
  );
}

function FormField({ label, children }) {
  return (
    <div>
      <label className="block text-[11px] font-medium text-[#86868b] uppercase tracking-[0.07em] mb-1.5">{label}</label>
      {children}
    </div>
  );
}

const inputCls = "w-full px-3.5 py-2.5 bg-[#f5f5f7] border border-[#e5e5ea] rounded-xl text-sm text-[#1d1d1f] focus:outline-none focus:border-[#0071e3] focus:bg-white transition-all";

function ProfileModal({ user, onClose, onSave }) {
  const [form, setForm] = useState({
    name: user.name || "", dob: user.dob || "", gender: user.gender || "",
    smoking_status: user.smoking_status || "non-smoker",
    marital_status: user.marital_status || "single",
    num_children: user.num_children || 0
  });

  return (
    <ModalShell title="Personal Profile" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onSave(form); }} className="p-6 space-y-4">
        <FormField label="Full Name">
          <input required className={inputCls} value={form.name} onChange={e => setForm({...form, name: e.target.value})} />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Date of Birth">
            <input type="date" className={inputCls} value={form.dob} onChange={e => setForm({...form, dob: e.target.value})} />
          </FormField>
          <FormField label="Gender">
            <select className={inputCls} value={form.gender} onChange={e => setForm({...form, gender: e.target.value})}>
              <option value="">Select…</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
              <option value="other">Other</option>
            </select>
          </FormField>
          <FormField label="Smoking">
            <select className={inputCls} value={form.smoking_status} onChange={e => setForm({...form, smoking_status: e.target.value})}>
              <option value="non-smoker">Non-Smoker</option>
              <option value="smoker">Smoker</option>
            </select>
          </FormField>
          <FormField label="Marital Status">
            <select className={inputCls} value={form.marital_status} onChange={e => setForm({...form, marital_status: e.target.value})}>
              <option value="single">Single</option>
              <option value="married">Married</option>
              <option value="divorced">Divorced</option>
              <option value="widowed">Widowed</option>
            </select>
          </FormField>
        </div>
        <FormField label="Children">
          <input type="number" min="0" className={inputCls} value={form.num_children} onChange={e => setForm({...form, num_children: parseInt(e.target.value)})} />
        </FormField>
        <div className="flex gap-3 pt-2">
          <button type="submit" className="flex-1 bg-[#0071e3] text-white py-2.5 rounded-xl text-sm font-medium hover:bg-[#0077ed] transition-colors">Save Profile</button>
          <button type="button" onClick={onClose} className="px-5 py-2.5 bg-[#f5f5f7] text-[#1d1d1f] rounded-xl text-sm font-medium hover:bg-[#e5e5ea] transition-colors">Cancel</button>
        </div>
      </form>
    </ModalShell>
  );
}

function PolicyModal({ policy, onClose, onSave }) {
  const [form, setForm] = useState(policy || {
    insurance_name: "", status: "in_effect", policy_document_url: "",
    starting_year: new Date().getFullYear(), payment_years: 20,
    coverage_years: 99, annual_premium: 0, coverage_amount: 0,
    category: "life", type: "personal"
  });
  const [isParsing, setIsParsing] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setIsParsing(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const resp = await fetch("/api/policies/parse", { method: "POST", body });
      const res = await resp.json();
      if (res.success && res.data) {
        const d = res.data;
        setForm(prev => ({
          ...prev,
          insurance_name: d.insurance_name || prev.insurance_name,
          payment_years: d.payment_years || prev.payment_years,
          coverage_years: d.coverage_years || prev.coverage_years,
          annual_premium: d.annual_premium || prev.annual_premium,
          coverage_amount: d.coverage_amount || prev.coverage_amount,
          policy_document_url: res.document_url || prev.policy_document_url
        }));
      } else { alert(res.error || "Failed to parse document"); }
    } catch { alert("Error uploading file"); }
    finally { setIsParsing(false); }
  };

  return (
    <ModalShell title={policy ? "Edit Policy" : "Add Policy"} onClose={onClose}>
      <div className="px-6 pt-4">
        <div className={`relative border-2 border-dashed rounded-xl p-4 transition-all ${isParsing ? 'bg-[#e8f2ff] border-[#0071e3]/40' : 'bg-[#f5f5f7] border-[#d2d2d7] hover:border-[#0071e3]/40'}`}>
          <input type="file" className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed" onChange={handleFileUpload} disabled={isParsing} accept=".pdf" />
          <div className="text-center">
            {isParsing ? (
              <div className="flex flex-col items-center gap-1.5">
                <div className="w-5 h-5 border-2 border-[#0071e3] border-t-transparent rounded-full animate-spin" />
                <p className="text-xs font-medium text-[#0071e3]">Parsing document…</p>
              </div>
            ) : (
              <>
                <p className="text-sm font-medium text-[#1d1d1f]">Upload Policy PDF</p>
                <p className="text-[11px] text-[#86868b] mt-0.5">Auto-fill details with AI</p>
              </>
            )}
          </div>
        </div>
      </div>
      <form onSubmit={(e) => { e.preventDefault(); onSave(form); }} className="p-6 space-y-4">
        <FormField label="Category">
          <select className={inputCls} value={form.category} onChange={e => setForm({...form, category: e.target.value})}>
            <option value="life">Life Insurance</option>
            <option value="medical">Medical Insurance</option>
            <option value="accident">Accident Insurance</option>
          </select>
        </FormField>
        {form.category === 'medical' && (
          <FormField label="Policy Type">
            <select className={inputCls} value={form.type} onChange={e => setForm({...form, type: e.target.value})}>
              <option value="personal">Personal</option>
              <option value="corporate">Corporate</option>
            </select>
          </FormField>
        )}
        <FormField label="Policy Name">
          <input required className={inputCls} placeholder="e.g. AIA Pro Lifetime Protector" value={form.insurance_name} onChange={e => setForm({...form, insurance_name: e.target.value})} />
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Status">
            <select className={inputCls} value={form.status} onChange={e => setForm({...form, status: e.target.value})}>
              <option value="in_effect">In Effect</option>
              <option value="lapsed">Lapsed</option>
              <option value="surrendered">Surrendered</option>
            </select>
          </FormField>
          <FormField label="Start Year">
            <input type="number" className={inputCls} value={form.starting_year} onChange={e => setForm({...form, starting_year: parseInt(e.target.value)})} />
          </FormField>
        </div>
        {form.category === 'life' && (
          <div className="grid grid-cols-2 gap-4">
            <FormField label="Pay Term (yr)">
              <input type="number" className={inputCls} value={form.payment_years} onChange={e => setForm({...form, payment_years: parseInt(e.target.value)})} />
            </FormField>
            <FormField label="Cover Term (yr)">
              <input type="number" className={inputCls} value={form.coverage_years} onChange={e => setForm({...form, coverage_years: parseInt(e.target.value)})} />
            </FormField>
            <FormField label="Annual (S$)">
              <input type="number" step="0.01" className={inputCls} value={form.annual_premium} onChange={e => setForm({...form, annual_premium: parseFloat(e.target.value)})} />
            </FormField>
            <FormField label="Sum Assured (S$)">
              <input type="number" className={inputCls} value={form.coverage_amount} onChange={e => setForm({...form, coverage_amount: parseInt(e.target.value)})} />
            </FormField>
          </div>
        )}
        <div className="flex gap-3 pt-2">
          <button type="submit" className="flex-1 bg-[#0071e3] text-white py-2.5 rounded-xl text-sm font-medium hover:bg-[#0077ed] transition-colors">Save</button>
          <button type="button" onClick={onClose} className="px-5 py-2.5 bg-[#f5f5f7] text-[#1d1d1f] rounded-xl text-sm font-medium hover:bg-[#e5e5ea] transition-colors">Cancel</button>
        </div>
      </form>
    </ModalShell>
  );
}

function TestClaimingModal({ onClose, onStartTest }) {
  const [form, setForm] = useState({ patient_age: "", ground_truth: "", stage: "", costs: "" });
  const [isGenerating, setIsGenerating] = useState(false);

  const handleRandomize = async () => {
    setIsGenerating(true);
    try {
      const resp = await fetch("/api/test_claim/random", { method: "POST" });
      const data = await resp.json();
      setForm(data);
    } catch { } finally { setIsGenerating(false); }
  };

  return (
    <ModalShell title="Test Claiming Strategy" onClose={onClose}>
      <form onSubmit={(e) => { e.preventDefault(); onStartTest(form); }} className="p-6 space-y-4">
        <div className="flex justify-end -mt-2">
          <button type="button" onClick={handleRandomize} disabled={isGenerating}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium text-[#7c3aed] bg-[#faf5ff] border border-[#e9d5ff] hover:bg-[#f3e8ff] transition-colors disabled:opacity-50">
            {isGenerating ? 'Generating…' : '🎲 Random Scenario'}
          </button>
        </div>
        <FormField label="Patient Age">
          <input required className={inputCls} value={form.patient_age} onChange={e => setForm({...form, patient_age: e.target.value})} />
        </FormField>
        <FormField label="Ground Truth Condition">
          <input required className={inputCls} value={form.ground_truth} onChange={e => setForm({...form, ground_truth: e.target.value})} />
        </FormField>
        <FormField label="Current Stage">
          <input required className={inputCls} value={form.stage} onChange={e => setForm({...form, stage: e.target.value})} />
        </FormField>
        <FormField label="Incurred Costs">
          <input required className={inputCls} value={form.costs} onChange={e => setForm({...form, costs: e.target.value})} />
        </FormField>
        <div className="flex gap-3 pt-2">
          <button type="submit" className="flex-1 bg-[#7c3aed] text-white py-2.5 rounded-xl text-sm font-medium hover:bg-[#6d28d9] transition-colors">Generate Strategy</button>
          <button type="button" onClick={onClose} className="px-5 py-2.5 bg-[#f5f5f7] text-[#1d1d1f] rounded-xl text-sm font-medium hover:bg-[#e5e5ea] transition-colors">Cancel</button>
        </div>
      </form>
    </ModalShell>
  );
}

// ─── Dashboard View ───────────────────────────────────────────────────────────

function DashboardView({ user, policies, onAddPolicy, onEditPolicy, onDeletePolicy, onStartAdvice, onTestClaim, onLogout }) {
  return (
    <div className="min-h-screen bg-[#f5f5f7]">
      {/* Header */}
      <header className="bg-white border-b border-[#e5e5ea] px-8 py-3.5 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-[#0071e3] flex items-center justify-center text-white text-lg">🛡️</div>
          <div>
            <h1 className="text-base font-semibold text-[#1d1d1f] tracking-tight leading-none">Insurance Central</h1>
            <p className="text-[11px] text-[#86868b] mt-0.5">Portfolio Management</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <button onClick={onTestClaim}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium text-[#7c3aed] bg-[#faf5ff] border border-[#e9d5ff] hover:bg-[#f3e8ff] transition-colors">
            🧪 Test Claiming
          </button>
          <button onClick={onStartAdvice}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium text-white bg-[#0071e3] hover:bg-[#0077ed] transition-colors">
            Get Advice
          </button>
          <div className="h-5 w-px bg-[#e5e5ea]" />
          <div className="flex items-center gap-2.5">
            <img src={user.picture} className="w-8 h-8 rounded-full border border-[#e5e5ea]" />
            <div className="text-sm">
              <div className="font-medium text-[#1d1d1f] leading-none mb-1">{user.name}</div>
              <div className="flex gap-3">
                <button onClick={() => window.showProfileModal()} className="text-[11px] text-[#0071e3] hover:underline leading-none">Edit</button>
                <button onClick={onLogout} className="text-[11px] text-[#86868b] hover:text-[#e11d48] leading-none transition-colors">Sign out</button>
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-8 py-8">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-semibold text-[#1d1d1f] tracking-tight">Coverage Portfolio</h2>
          <button onClick={() => onAddPolicy()}
            className="flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium text-[#0071e3] bg-white border border-[#d2d2d7] hover:border-[#0071e3] transition-colors">
            + Add Policy
          </button>
        </div>

        {policies.length === 0 ? (
          <div className="bg-white rounded-2xl p-16 text-center border border-[#e5e5ea] flex flex-col items-center">
            <div className="w-16 h-16 rounded-2xl bg-[#f5f5f7] flex items-center justify-center text-4xl mb-5 opacity-60">📄</div>
            <h3 className="text-xl font-semibold text-[#1d1d1f] mb-2 tracking-tight">Portfolio is empty</h3>
            <p className="text-[#6e6e73] text-sm max-w-xs mb-8 leading-relaxed">Record your existing insurance policies to track premiums and identify coverage gaps.</p>
            <button onClick={() => onAddPolicy()} className="px-6 py-2.5 bg-[#0071e3] text-white rounded-full text-sm font-medium hover:bg-[#0077ed] transition-colors">Add Your First Policy</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {policies.map(p => (
              <div key={p.id} className="bg-white rounded-2xl p-6 border border-[#e5e5ea] hover:border-[#d2d2d7] transition-colors group relative">
                <div className="absolute top-4 right-4 opacity-0 group-hover:opacity-100 transition-opacity flex gap-1.5">
                  <button onClick={() => onEditPolicy(p)} className="w-7 h-7 bg-[#f5f5f7] rounded-lg text-[#86868b] hover:text-[#0071e3] hover:bg-[#e8f2ff] flex items-center justify-center text-sm transition-colors">✎</button>
                  <button onClick={() => onDeletePolicy(p.id)} className="w-7 h-7 bg-[#f5f5f7] rounded-lg text-[#86868b] hover:text-[#e11d48] hover:bg-[#fff1f2] flex items-center justify-center text-lg leading-none transition-colors">&times;</button>
                </div>

                <div className="mb-4">
                  <Tag color={p.status === 'in_effect' ? 'green' : p.status === 'lapsed' ? 'amber' : 'red'}>
                    {p.status.replace('_', ' ')}
                  </Tag>
                </div>

                <h3 className="text-base font-semibold text-[#1d1d1f] mb-5 leading-snug line-clamp-2">{p.insurance_name}</h3>

                {p.category === 'life' && (
                  <div className="grid grid-cols-2 gap-5 mb-5">
                    <div>
                      <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-1">Sum Assured</div>
                      <div className="text-sm font-semibold text-[#1d1d1f]">S$ {(p.coverage_amount || 0).toLocaleString()}</div>
                      <div className="text-[10px] text-[#86868b] mt-1">Until {p.starting_year + (p.coverage_years || 0)}</div>
                    </div>
                    <div>
                      <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-1">Annual Premium</div>
                      <div className="text-sm font-semibold text-[#0071e3]">S$ {(p.annual_premium || 0).toLocaleString()}</div>
                      <div className="text-[10px] text-[#86868b] mt-1">{p.payment_years || 0}yr pay term</div>
                    </div>
                  </div>
                )}
                {p.category === 'medical' && (
                  <div className="mb-5">
                    <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-1">Policy Type</div>
                    <div className="text-sm font-semibold text-[#1d1d1f] capitalize">{p.type || 'Personal'}</div>
                    <div className="text-[10px] text-[#86868b] mt-1">Since {p.starting_year}</div>
                  </div>
                )}
                {p.category === 'accident' && (
                  <div className="mb-5">
                    <div className="text-[10px] font-medium text-[#86868b] uppercase tracking-wider mb-1">Inception Year</div>
                    <div className="text-sm font-semibold text-[#1d1d1f]">{p.starting_year}</div>
                  </div>
                )}

                {p.policy_document_url && (
                  <div className="pt-4 border-t border-[#f5f5f7]">
                    <a href={p.policy_document_url} target="_blank"
                      className="text-[11px] font-medium text-[#0071e3] flex items-center gap-1.5 hover:underline">
                      📄 View Document →
                    </a>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}

// ─── Sidebar ─────────────────────────────────────────────────────────────────

function ConversationSidebar({ open, sessionType, conversations, activeId, onLoad, onNew, onRename, onDelete }) {
  return (
    <div className={`transition-all duration-300 bg-white border-r border-[#e5e5ea] flex flex-col flex-shrink-0 ${open ? 'w-56' : 'w-0 overflow-hidden border-none'}`}>
      <div className="px-4 py-3 border-b border-[#f5f5f7] flex items-center justify-between flex-shrink-0">
        <span className="text-[11px] font-semibold text-[#86868b] uppercase tracking-[0.07em]">History</span>
        <button onClick={onNew} className="flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-medium text-[#0071e3] bg-[#e8f2ff] hover:bg-[#d4e9ff] transition-colors">
          + New
        </button>
      </div>
      <div className="flex-1 overflow-y-auto py-2 px-2 space-y-0.5">
        {conversations.map(c => (
          <div
            key={c.id}
            className={`group relative w-full text-left px-3 py-2.5 rounded-xl transition-all cursor-pointer ${activeId === c.id ? 'bg-[#e8f2ff] text-[#0071e3]' : 'text-[#1d1d1f] hover:bg-[#f5f5f7]'}`}
            onClick={() => onLoad(c)}
          >
            <div className="text-xs font-medium truncate pr-10 leading-snug">{c.title || "New Conversation"}</div>
            <div className={`text-[10px] mt-0.5 ${activeId === c.id ? 'text-[#0071e3]/70' : 'text-[#86868b]'}`}>
              {new Date(c.updated_at + "Z").toLocaleString()}
            </div>
            <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity flex gap-0.5">
              <button onClick={(e) => onRename(e, c.id, c.title)}
                className={`w-5 h-5 rounded flex items-center justify-center text-[10px] ${activeId === c.id ? 'hover:bg-[#0071e3]/20' : 'hover:bg-[#e8f2ff] hover:text-[#0071e3]'}`}>✎</button>
              <button onClick={(e) => onDelete(e, c.id)}
                className={`w-5 h-5 rounded flex items-center justify-center text-sm leading-none ${activeId === c.id ? 'hover:bg-[#0071e3]/20' : 'hover:bg-[#fff1f2] hover:text-[#e11d48]'}`}>&times;</button>
            </div>
          </div>
        ))}
        {conversations.length === 0 && (
          <div className="text-center py-6 text-xs text-[#86868b]">No history</div>
        )}
      </div>
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────

function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("dashboard");
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [profileModal, setProfileModal] = useState(false);
  const [testClaimModal, setTestClaimModal] = useState(false);
  const [conversations, setConversations] = useState([]);
  const [testConversations, setTestConversations] = useState([]);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);

  window.showProfileModal = () => setProfileModal(true);

  const [cd, setCd] = useState({
    sessionId: null, messages: [], isWaiting: false, isTyping: false,
    phase: "idle", activeTab: "requirements",
    requirements: null, criteria: null, policies: null,
    activeAgent: null, claimData: null, testParams: null, sessionType: "advice"
  });

  const wsRef = useRef(null);

  useEffect(() => { fetchUser(); }, []);

  const fetchUser = async () => {
    try {
      const r = await fetch("/api/auth/me");
      const d = await r.json();
      if (d.logged_in) { setUser(d.user); fetchPolicies(); fetchConversations(); }
    } catch (e) {} finally { setLoading(false); }
  };

  const fetchPolicies = async () => {
    try { const r = await fetch("/api/policies"); const d = await r.json(); setPolicies(d.policies || []); } catch (e) {}
  };

  const fetchConversations = async () => {
    try {
      const [aR, tR] = await Promise.all([fetch("/api/conversations?type=advice"), fetch("/api/conversations?type=test")]);
      const aD = await aR.json(); const tD = await tR.json();
      setConversations(aD.conversations || []);
      setTestConversations(tD.conversations || []);
    } catch (e) {}
  };

  const savePolicy = async (data) => {
    const isEdit = !!data.id;
    const r = await fetch(isEdit ? `/api/policies/${data.id}` : "/api/policies", {
      method: isEdit ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (r.ok) { setModal(null); fetchPolicies(); }
  };

  const saveProfile = async (data) => {
    const r = await fetch("/api/auth/profile", { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    if (r.ok) { const res = await r.json(); setUser(res.user); setProfileModal(false); }
  };

  const deletePolicy = async (id) => {
    if (confirm("Remove this policy?")) { await fetch(`/api/policies/${id}`, { method: "DELETE" }); fetchPolicies(); }
  };

  const handleMsg = (raw) => {
    const d = JSON.parse(raw);
    setCd(prev => {
      const next = { ...prev };
      switch (d.type) {
        case "question":     next.isTyping = false; next.messages = [...next.messages, mkMsg("agent", d.content)]; next.isWaiting = true; break;
        case "status":       if (d.phase) next.phase = d.phase; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("status", d.message, d.phase)]; break;
        case "requirements": next.requirements = d.data; next.activeTab = "requirements"; next.activeAgent = "new_life_insurance"; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("milestone", "Profile captured")]; break;
        case "criteria":     next.criteria = d.data; next.activeTab = "criteria"; next.activeAgent = "new_life_insurance"; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("milestone", "Criteria generated")]; break;
        case "policies":     next.policies = d.data; next.activeTab = "policies"; next.activeAgent = "new_life_insurance"; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("milestone", "Evaluations complete")]; break;
        case "claim_update": next.claimData = d.data; next.activeAgent = "claiming_strategy"; break;
        case "test_scenario":    next.messages = [mkMsg("agent", `*Test Scenario Generated*\n\n${d.content}`)]; break;
        case "test_patient_msg": next.messages = [...next.messages, mkMsg("user", d.content)]; break;
        case "complete":     next.phase = "complete"; break;
      }
      return next;
    });
  };

  const handleSend = async (text) => {
    setCd(prev => ({...prev, messages: [...prev.messages, mkMsg("user", text)]}));
    if (!cd.sessionId) {
      const r = await fetch("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: cd.sessionType || "advice" }) });
      const { session_id } = await r.json();
      setCd(prev => ({...prev, sessionId: session_id}));
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/${session_id}`);
      wsRef.current = ws;
      ws.onopen = () => { setCd(prev => ({...prev, isTyping: true})); ws.send(JSON.stringify({ type: "start", message: text })); };
      ws.onmessage = (e) => handleMsg(e.data);
      fetchConversations();
    } else {
      setCd(prev => ({...prev, isWaiting: false, isTyping: true}));
      wsRef.current?.send(JSON.stringify({ type: "answer", content: text }));
    }
  };

  const loadConversation = async (conv) => {
    if (cd.sessionId === conv.id) return;
    if (wsRef.current) wsRef.current.close();

    let agent = null;
    if (conv.advice_entity === "claim") agent = "claiming_strategy";
    else if (conv.advice_entity === "purchase") agent = "new_life_insurance";
    else if (conv.type === "test" || conv.state_data?.claim_state) agent = "claiming_strategy";
    else if (conv.state_data?.user_requirements) agent = "new_life_insurance";

    setCd({
      sessionId: conv.id, messages: [], isWaiting: false, isTyping: false,
      phase: conv.phase || "idle",
      activeTab: conv.state_data?.policies ? "policies" : (conv.state_data?.criteria ? "criteria" : "requirements"),
      requirements: conv.state_data?.user_requirements || null,
      criteria: conv.state_data?.criteria || null,
      policies: conv.state_data?.policies || null,
      activeAgent: agent,
      claimData: agent === "claiming_strategy" ? { ...(conv.state_data?.claim_state || {}), details: conv.state_data?.claim_state || {} } : null,
      testParams: conv.state_data?.test_params || null,
      sessionType: conv.type || "advice"
    });

    try {
      const r = await fetch(`/api/conversations/${conv.id}/messages`);
      const data = await r.json();
      const msgs = data.messages.map(m => {
        const raw = m.raw_data || {};
        if (raw.type === "user") return mkMsg("user", raw.content);
        if (raw.type === "question") return mkMsg("agent", raw.content || m.content);
        if (raw.type === "status") return mkMsg("status", raw.message || raw.content || m.content, raw.phase);
        if (raw.type === "complete") return mkMsg("milestone", raw.message || raw.content || m.content);
        if (raw.type === "error") return mkMsg("error", raw.message || raw.content || m.content);
        if (m.role === "user") return mkMsg("user", m.content);
        return mkMsg("agent", m.content);
      });
      setCd(prev => ({...prev, messages: msgs}));
    } catch (e) {}

    setView("consultant");
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/${conv.id}`);
    wsRef.current = ws;
    ws.onmessage = (e) => handleMsg(e.data);
  };

  const handleStartAdvice = () => {
    setCd({ sessionId: null, messages: [], isWaiting: false, isTyping: false, phase: "idle", activeTab: "requirements", requirements: null, criteria: null, policies: null, activeAgent: null, claimData: null, testParams: null, sessionType: "advice" });
    fetchConversations();
    setView("consultant");
  };

  const handleStartTestClaim = async (params) => {
    setTestClaimModal(false);
    setCd({ sessionId: null, messages: [], isWaiting: false, isTyping: true, phase: "idle", activeTab: "requirements", requirements: null, criteria: null, policies: null, activeAgent: "claiming_strategy", claimData: { details: {} }, testParams: params, sessionType: "test" });

    const r = await fetch("/api/sessions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type: "test" }) });
    const { session_id } = await r.json();
    setCd(prev => ({...prev, sessionId: session_id}));

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const ws = new WebSocket(`${proto}//${window.location.host}/ws/${session_id}`);
    wsRef.current = ws;
    ws.onopen = () => { ws.send(JSON.stringify({ type: "start_test", params })); };
    ws.onmessage = (e) => handleMsg(e.data);
    fetchConversations();
    setView("consultant");
  };

  const handleRename = async (e, id, old) => {
    e.stopPropagation();
    const t = prompt("Rename:", old || "New Conversation");
    if (t && t.trim() !== "" && t !== old) {
      await fetch(`/api/conversations/${id}/title`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: t.trim() }) });
      fetchConversations();
    }
  };

  const handleDeleteConv = async (e, id) => {
    e.stopPropagation();
    if (confirm("Delete this conversation?")) {
      await fetch(`/api/conversations/${id}`, { method: "DELETE" });
      if (cd.sessionId === id) handleStartAdvice();
      else fetchConversations();
    }
  };

  if (loading) return (
    <div className="h-screen flex items-center justify-center bg-[#f5f5f7]">
      <div className="w-10 h-10 border-2 border-[#0071e3] border-t-transparent rounded-full animate-spin" />
    </div>
  );

  if (!user) return (
    <div className="h-screen flex items-center justify-center bg-[#f5f5f7] p-6">
      <div className="bg-white p-10 rounded-2xl shadow-sm max-w-sm w-full text-center border border-[#e5e5ea]">
        <div className="w-16 h-16 rounded-2xl bg-[#0071e3] flex items-center justify-center text-white text-3xl mx-auto mb-6">🛡️</div>
        <h1 className="text-2xl font-semibold text-[#1d1d1f] mb-2 tracking-tight">Insurance Central</h1>
        <p className="text-[#6e6e73] text-sm mb-8 leading-relaxed">AI-powered insurance advice,<br />personalised to your needs.</p>
        <a href="/api/auth/login"
          className="block w-full bg-[#0071e3] text-white py-3 rounded-full text-sm font-medium hover:bg-[#0077ed] transition-colors">
          Continue with Google
        </a>
      </div>
    </div>
  );

  return (
    <div className="h-screen w-full">
      {view === "consultant" ? (
        <div className="h-screen flex flex-col bg-[#f5f5f7]">
          {/* ── Slim header ── */}
          <header className="flex-none h-11 bg-white border-b border-[#e5e5ea] px-4 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <IconButton onClick={() => setView("dashboard")} title="Back to Dashboard">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 2L4 6.5 8 11"/>
                </svg>
              </IconButton>
              <IconButton onClick={() => setIsSidebarOpen(!isSidebarOpen)} title="Toggle history">
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                  <path d="M2 3h9M2 6.5h9M2 10h9"/>
                </svg>
              </IconButton>
              <span className="text-sm font-medium text-[#1d1d1f] ml-1">
                {cd.sessionType === "test" ? "Scenario Testing" : "Expert Advice"}
              </span>
            </div>

            <div className="flex items-center gap-3">
              {cd.activeAgent === "new_life_insurance" && <PhaseBar phase={cd.phase} />}
              {cd.activeAgent === "claiming_strategy" && (
                <Tag color="blue">
                  <span className="pulse-dot w-1.5 h-1.5 rounded-full bg-[#0071e3] inline-block mr-1.5" />
                  Claim Engine
                </Tag>
              )}
            </div>
          </header>

          {/* ── Main area ── */}
          <div className="flex-1 min-h-0 flex overflow-hidden">

            {/* Sidebar */}
            <ConversationSidebar
              open={isSidebarOpen}
              sessionType={cd.sessionType}
              conversations={cd.sessionType === "test" ? testConversations : conversations}
              activeId={cd.sessionId}
              onLoad={loadConversation}
              onNew={cd.sessionType === "test" ? () => setTestClaimModal(true) : handleStartAdvice}
              onRename={handleRename}
              onDelete={handleDeleteConv}
            />

            {/* Chat column */}
            <div className={`flex flex-col bg-white ${cd.activeAgent ? 'w-[400px] flex-shrink-0 border-r border-[#e5e5ea]' : 'flex-1 max-w-2xl border-x border-[#e5e5ea] mx-auto'}`}>
              {cd.testParams && (
                <div className="bg-[#faf5ff] border-b border-[#e9d5ff] px-4 py-2 flex flex-wrap gap-4 text-xs flex-shrink-0">
                  {[['Age', cd.testParams.patient_age], ['Condition', cd.testParams.ground_truth], ['Stage', cd.testParams.stage], ['Costs', cd.testParams.costs]].map(([k, v]) => (
                    <div key={k} className="flex items-center gap-1">
                      <span className="font-semibold text-[#7c3aed]">{k}:</span>
                      <span className="text-[#6d28d9]">{v}</span>
                    </div>
                  ))}
                </div>
              )}
              <ChatPanel
                messages={cd.messages}
                isWaitingAnswer={cd.isWaiting}
                isTyping={cd.isTyping}
                phase={cd.phase}
                onSend={handleSend}
                isStarted={!!cd.sessionId}
              />
            </div>

            {/* Data panel */}
            {cd.activeAgent && (
              <div className="flex-1 min-w-0 flex flex-col overflow-hidden bg-[#f5f5f7]">
                {cd.activeAgent === "new_life_insurance" && (
                  <>
                    <div className="bg-white border-b border-[#e5e5ea] flex px-5 pt-3.5 flex-shrink-0">
                      {['requirements', 'criteria', 'policies'].map(t => (
                        <button
                          key={t}
                          onClick={() => setCd(prev => ({...prev, activeTab: t}))}
                          className={`px-3 pb-3 text-xs font-medium transition-all mr-4 border-b-2 capitalize ${cd.activeTab === t ? 'text-[#0071e3] border-[#0071e3]' : 'text-[#86868b] border-transparent hover:text-[#6e6e73]'}`}
                        >
                          {t}
                        </button>
                      ))}
                    </div>
                    <div className="flex-1 min-h-0 overflow-hidden">
                      {cd.activeTab === 'requirements' && <RequirementsView data={cd.requirements} />}
                      {cd.activeTab === 'criteria'     && <CriteriaView    data={cd.criteria} />}
                      {cd.activeTab === 'policies'     && <PoliciesView    data={cd.policies} />}
                    </div>
                  </>
                )}
                {cd.activeAgent === "claiming_strategy" && <ClaimingPanel data={cd.claimData} />}
              </div>
            )}
          </div>
        </div>
      ) : (
        <DashboardView
          user={user} policies={policies}
          onAddPolicy={() => setModal({})} onEditPolicy={(p) => setModal(p)}
          onDeletePolicy={deletePolicy} onStartAdvice={handleStartAdvice}
          onTestClaim={() => {
            setCd(prev => ({ ...prev, sessionType: "test" }));
            setView("consultant");
            setTestClaimModal(true);
          }}
          onLogout={() => window.location.href = "/api/auth/logout"}
        />
      )}

      {modal        && <PolicyModal policy={modal.id ? modal : null} onClose={() => setModal(null)} onSave={savePolicy} />}
      {profileModal && <ProfileModal user={user} onClose={() => setProfileModal(false)} onSave={saveProfile} />}
      {testClaimModal && <TestClaimingModal onClose={() => setTestClaimModal(false)} onStartTest={handleStartTestClaim} />}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
