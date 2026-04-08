/* global React, ReactDOM */
const { useState, useEffect, useRef, useCallback } = React;

// ─── Helpers ────────────────────────────────────────────────────────────────

let _msgId = 0;
function mkMsg(type, content, statusPhase) {
  return { id: String(++_msgId), type, content, statusPhase };
}

// ─── Shared Components ──────────────────────────────────────────────────────

function PhaseBar({ phase }) {
  const PHASES = ["profile", "criteria", "fetching", "retrieval", "scoring", "complete"];
  const LABELS = {
    profile: "Profile", criteria: "Criteria", fetching: "Fetching",
    retrieval: "Retrieval", scoring: "Scoring", complete: "Complete",
  };
  const cur = PHASES.indexOf(phase);
  return (
    <div className="flex items-center gap-1 text-xs select-none">
      {PHASES.map((p, i) => (
        <React.Fragment key={p}>
          <span className={`px-2 py-0.5 rounded-full font-medium transition-all ${i < cur ? "bg-green-100 text-green-700" :
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

function TypingBubble() {
  return (
    <div className="flex justify-start mb-3 gap-2 msg-enter">
      <div className="w-7 h-7 rounded-full bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-bold shadow-sm">
        AI
      </div>
      <div className="bg-white border border-gray-100 shadow-sm rounded-2xl rounded-bl-sm px-4 py-3 flex items-center gap-1.5">
        <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "0ms" }} />
        <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "150ms" }} />
        <span className="w-2 h-2 bg-gray-300 rounded-full animate-bounce" style={{ animationDelay: "300ms" }} />
      </div>
    </div>
  );
}

function ChatMessage({ msg }) {
  if (msg.type === "status") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-blue-50 border border-blue-100 text-blue-600 text-[10px] font-bold uppercase tracking-wider">
          <span className="pulse-dot w-1.5 h-1.5 rounded-full bg-blue-400 inline-block" />
          {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "milestone") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-green-50 border border-green-100 text-green-700 text-[10px] font-bold uppercase tracking-wider">
          <span>✓</span>{msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "error") {
    return (
      <div className="flex justify-center my-2 msg-enter">
        <span className="px-3 py-1.5 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs max-w-xs text-center font-bold">
          ⚠ {msg.content}
        </span>
      </div>
    );
  }
  if (msg.type === "user") {
    return (
      <div className="flex justify-end mb-4 msg-enter">
        <div className="max-w-[85%] bg-blue-600 text-white rounded-3xl rounded-br-none px-5 py-3 text-sm font-medium leading-relaxed shadow-lg shadow-blue-100">
          {msg.content}
        </div>
      </div>
    );
  }
  // agent
  return (
    <div className="flex justify-start mb-4 gap-3 msg-enter">
      <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-600 flex items-center justify-center flex-shrink-0 mt-0.5 text-xs font-black shadow-sm">
        AI
      </div>
      <div className="max-w-[85%] bg-white border border-gray-100 shadow-sm rounded-3xl rounded-bl-none px-5 py-3 text-sm leading-relaxed text-gray-800 whitespace-pre-wrap font-medium">
        {msg.content}
      </div>
    </div>
  );
}

function ChatPanel({ messages, isWaitingAnswer, isTyping, phase, onSend, isStarted }) {
  const [input, setInput] = useState("");
  const endRef = useRef(null);
  const textareaRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages]);

  useEffect(() => {
    const ta = textareaRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [input]);

  const isProcessing = ["criteria", "fetching", "retrieval", "scoring"].includes(phase) && !isWaitingAnswer;

  const placeholder = !isStarted
    ? "How can I help you today?"
    : isWaitingAnswer ? "Type your answer..."
      : isProcessing ? "Thinking..."
        : "Type a message...";

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
    <div className="flex flex-col h-full bg-white">
      <div className="flex-1 overflow-y-auto p-6">
        {messages.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full text-center px-6">
            <div className="w-20 h-20 rounded-[2.5rem] bg-blue-50 flex items-center justify-center text-4xl mb-6 shadow-inner ring-8 ring-blue-50/50">🛡️</div>
            <h3 className="text-xl font-black text-gray-900 mb-2 tracking-tight">AI Insurance Advisor</h3>
            <p className="text-gray-400 text-sm max-w-xs mx-auto font-medium">I'm here to help you find the best coverage based on your profile and needs.</p>
          </div>
        )}
        {messages.map((m) => <ChatMessage key={m.id} msg={m} />)}
        {isTyping && <TypingBubble />}
        <div ref={endRef} />
      </div>

      <div className="p-6 bg-white flex-shrink-0 border-t border-gray-50">
        <form onSubmit={handleSubmit} className="flex items-end gap-3 bg-slate-50 p-2 rounded-[2rem] border border-gray-100 focus-within:border-blue-400 focus-within:ring-4 focus-within:ring-blue-50 transition-all duration-300">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={placeholder}
            disabled={isProcessing}
            className="flex-1 px-4 py-2 bg-transparent text-sm font-medium focus:outline-none disabled:opacity-40 transition resize-none overflow-y-auto leading-relaxed"
            style={{ minHeight: "40px", maxHeight: "160px" }}
          />
          <button
            type="submit"
            disabled={isProcessing || !input.trim()}
            className="w-12 h-12 bg-blue-600 text-white rounded-full flex items-center justify-center hover:bg-blue-700 disabled:opacity-40 disabled:cursor-not-allowed transition-all shadow-lg shadow-blue-100 flex-shrink-0"
          >
            <span className="text-2xl font-bold">➔</span>
          </button>
        </form>
        <p className="text-[10px] text-gray-300 mt-3 ml-2 font-bold uppercase tracking-widest select-none">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}

function RequirementItemCard({ item }) {
  const displayValue = Array.isArray(item.value)
    ? item.value.join(", ")
    : item.value === true ? "Yes"
      : item.value === false ? "No"
        : String(item.value ?? "—");

  return (
    <div className="bg-white rounded-3xl p-5 border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between gap-2 mb-3">
        <span className="text-[10px] text-gray-400 font-extrabold uppercase tracking-[0.1em]">{item.label}</span>
        <div className="flex items-center gap-2">
          {item.confirmed_by_user && <span className="text-[10px] text-green-600 font-black">✓ OK</span>}
          <span className="text-[10px] px-2 py-0.5 rounded-full border border-gray-100 bg-gray-50 text-gray-500 font-black uppercase">{item.source}</span>
        </div>
      </div>
      <div className="text-sm font-black text-gray-900 leading-snug">{displayValue}</div>
      {item.reasoning && (
        <div className="text-[11px] text-gray-400 mt-3 pt-3 border-t border-gray-50 font-medium italic leading-relaxed">{item.reasoning}</div>
      )}
    </div>
  );
}

function RequirementsView({ data }) {
  if (!data?.items?.length) return (
    <div className="h-full flex flex-col items-center justify-center text-gray-400 p-8 grayscale opacity-50">
      <div className="text-6xl mb-4">👤</div>
      <p className="font-bold text-sm">Dynamic profile building...</p>
    </div>
  );

  return (
    <div className="p-6 space-y-4 overflow-y-auto h-full bg-slate-50/50">
      {data.items.map(item => <RequirementItemCard key={item.key} item={item} />)}
    </div>
  );
}

function CriterionCard({ item }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="bg-white rounded-3xl border border-gray-100 overflow-hidden shadow-sm shadow-blue-50/20">
      <button
        className="w-full p-5 text-left flex items-center gap-4 hover:bg-slate-50/50 transition-colors"
        onClick={() => setOpen(!open)}
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-3">
            <span className="text-sm font-black text-gray-900 truncate tracking-tight">{item.item}</span>
            <span className="text-[10px] font-black text-blue-600 bg-blue-50 px-2.5 py-1 rounded-xl shadow-sm ring-1 ring-blue-100">{item.weight}%</span>
          </div>
          <div className="w-full bg-slate-100 rounded-full h-2 shadow-inner">
            <div className="bg-blue-600 h-full rounded-full transition-all duration-700 shadow-lg shadow-blue-200" style={{ width: `${item.weight}%` }} />
          </div>
        </div>
        <span className="text-gray-300 transition-transform duration-300" style={{ transform: open ? 'rotate(180deg)' : 'none' }}>▼</span>
      </button>

      {open && (
        <div className="px-6 pb-6 pt-2 border-t border-gray-50 space-y-4 bg-slate-50/20">
          <div>
            <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1.5 opacity-60">Objective</div>
            <p className="text-xs text-gray-700 font-bold leading-relaxed">{item.description}</p>
          </div>
          <div className="p-3 bg-blue-50/30 rounded-2xl border border-blue-100/50">
            <div className="text-[10px] font-black text-blue-400 uppercase tracking-widest mb-1">Scoring Criteria</div>
            <p className="text-xs text-blue-800 font-black leading-relaxed">{item.scoring_rules}</p>
          </div>
        </div>
      )}
    </div>
  );
}

function CriteriaView({ data }) {
  if (!data?.criteria?.length && !data?.filters?.length) return (
    <div className="h-full flex flex-col items-center justify-center text-gray-400 p-8 grayscale opacity-50">
      <div className="text-6xl mb-4">📋</div>
      <p className="font-bold text-sm">Waiting for profile completion...</p>
    </div>
  );

  return (
    <div className="p-6 space-y-6 overflow-y-auto h-full bg-slate-50/50">
      {data.filters?.length > 0 && (
        <div className="mb-4">
          <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-2">
             <span className="w-1.5 h-1.5 bg-blue-600 rounded-full animate-pulse shadow-[0_0_8px_rgba(37,99,235,0.4)]"></span>
             Mandatory Filters (Must-Haves)
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {data.filters.map((f, i) => (
              <div key={i} className="flex items-center gap-3 bg-white p-4 rounded-2xl border border-gray-100 shadow-sm shadow-blue-50/10">
                <span className="text-blue-500 text-base">🛡️</span>
                <span className="text-xs font-black text-gray-800 tracking-tight leading-tight">{f}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div>
        <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-2">
           <span className="w-1.5 h-1.5 bg-purple-600 rounded-full"></span>
           Weighted Scoring Criteria
        </div>
        <div className="space-y-4">
          {data.criteria.map((c, i) => <CriterionCard key={i} item={c} />)}
        </div>
      </div>
    </div>
  );
}

function PolicyRankEntry({ policy, rank }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const totalScore = policy.scoring.reduce((s, [sc, crit]) => s + sc * (crit.weight / 100), 0);
  const colorClass = totalScore >= 4 ? "text-green-600" : totalScore >= 3 ? "text-amber-500" : "text-red-500";
  
  return (
    <div className={`bg-white rounded-[2rem] border border-gray-100 p-8 shadow-sm transition-all duration-500 mb-6 group relative ring-offset-2 hover:ring-2 ${isExpanded ? 'ring-blue-200 shadow-2xl scale-[1.02]' : 'ring-blue-50 shadow-sm hover:shadow-xl'}`}>
      <div className="flex items-start justify-between gap-6 mb-6">
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-3">
            <span className="w-10 h-10 rounded-2xl bg-slate-950 text-white flex items-center justify-center text-xs font-black shadow-lg shadow-slate-200">{rank}</span>
            <span className={`text-[10px] px-3 py-1.5 rounded-xl font-black uppercase tracking-wider border ${policy.fulfil_filters[0] ? 'bg-green-50 text-green-700 border-green-200' : 'bg-red-50 text-red-700 border-red-200'}`}>
              {policy.fulfil_filters[0] ? '✓ Eligible' : '✗ Ineligible'}
            </span>
          </div>
          <h4 className="font-black text-gray-900 text-xl tracking-tight leading-tight mb-2">{policy.policy_name}</h4>
          {!policy.fulfil_filters[0] && (
            <p className="text-[11px] text-red-400 font-bold leading-tight decoration-red-200 decoration-2 underline-offset-4 mb-2 italic">
               Reason: {policy.fulfil_filters[1]}
            </p>
          )}
        </div>
        <div className="text-right">
          <div className="text-[10px] font-black text-gray-300 uppercase tracking-widest mb-1">Match</div>
          <div className={`text-5xl font-black tabular-nums transition-colors duration-500 ${colorClass}`}>{totalScore.toFixed(1)}</div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-8 py-6 border-y border-gray-50 bg-slate-50/30 -mx-8 px-8 mb-4">
        <div>
          <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1.5 opacity-60">Estimated Premium</div>
          <div className="text-lg font-black text-blue-600 tabular-nums">{policy.basic_info.annual_premium}</div>
        </div>
        <div>
          <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1.5 opacity-60">ROI / Return Rate</div>
          <div className="flex items-center gap-3">
            <div className="text-lg font-black text-purple-600 tabular-nums">{(policy.return_rate * 100).toFixed(2)}%</div>
            {(policy.basic_info.product_summary_url || policy.basic_info.brochure_url) && (
              <div className="flex gap-2 ml-1">
                {policy.basic_info.product_summary_url && (
                  <a href={policy.basic_info.product_summary_url} target="_blank" className="w-6 h-6 rounded-full bg-blue-50 text-blue-600 flex items-center justify-center text-[10px] hover:bg-blue-600 hover:text-white transition-all shadow-sm" title="Product Summary">📄</a>
                )}
                {policy.basic_info.brochure_url && (
                  <a href={policy.basic_info.brochure_url} target="_blank" className="w-6 h-6 rounded-full bg-purple-50 text-purple-600 flex items-center justify-center text-[10px] hover:bg-purple-600 hover:text-white transition-all shadow-sm" title="Brochure">📖</a>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {isExpanded && (
        <div className="animate-slideDown space-y-8 pt-4">
          <div>
            <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-2">
               <span className="w-1 h-1 bg-blue-600 rounded-full"></span>
               Scoring Breakdown
            </div>
            <div className="space-y-3">
              {policy.scoring.map(([score, crit, reasoning], i) => (
                <div key={i} className="p-5 bg-slate-50/50 rounded-2xl border border-slate-100 ring-1 ring-white">
                  <div className="flex justify-between items-center mb-2">
                    <span className="text-[11px] font-black text-gray-900 tracking-tight">{crit.item}</span>
                    <span className={`text-sm font-black ${score >= 4 ? 'text-green-600' : score >= 3 ? 'text-amber-500' : 'text-red-500'}`}>{score}/5</span>
                  </div>
                  <p className="text-[11px] text-gray-500 font-medium leading-relaxed italic">{reasoning}</p>
                </div>
              ))}
            </div>
          </div>

          {(policy.context_summary && Object.keys(policy.context_summary).length > 0) && (
            <div>
              <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-4 flex items-center gap-2">
                 <span className="w-1 h-1 bg-purple-600 rounded-full"></span>
                 Deep Dive Summaries
              </div>
              <div className="space-y-4">
                {Object.entries(policy.context_summary).map(([title, text], i) => (
                  <div key={i} className="pl-4 border-l-2 border-slate-100">
                    <h5 className="text-[10px] font-black text-gray-900 uppercase tracking-widest mb-1.5">{title}</h5>
                    <p className="text-[11px] text-gray-500 font-bold leading-relaxed">{text}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}


      <button 
        onClick={() => setIsExpanded(!isExpanded)}
        className={`w-full mt-6 py-4 rounded-2xl text-[10px] font-black uppercase tracking-[0.2em] transition-all flex items-center justify-center gap-3 ${isExpanded ? 'bg-slate-900 text-white shadow-xl shadow-slate-200 ring-4 ring-slate-100' : 'bg-slate-50 text-gray-400 hover:bg-blue-600 hover:text-white hover:shadow-lg hover:shadow-blue-100'}`}
      >
        <span>{isExpanded ? 'Collapse Analysis' : 'Review Evaluation Details'}</span>
        <span className={`text-xs transition-transform duration-500 ${isExpanded ? 'rotate-180' : ''}`}>▼</span>
      </button>
    </div>
  );
}

function PoliciesView({ data }) {
  if (!data?.length) return (
    <div className="h-full flex flex-col items-center justify-center text-gray-400 p-8 grayscale opacity-50">
      <div className="text-6xl mb-4">📊</div>
      <p className="font-bold text-sm">Analyzing market options...</p>
    </div>
  );

  return (
    <div className="p-6 overflow-y-auto h-full bg-slate-50/50">
      {data.map((p, i) => <PolicyRankEntry key={i} policy={p} rank={i+1} />)}
    </div>
  );
}

// ─── Dashboard Components ────────────────────────────────────────────────────

function ProfileModal({ user, onClose, onSave }) {
  const [formData, setFormData] = useState({
    name: user.name || "",
    dob: user.dob || "",
    gender: user.gender || "",
    smoking_status: user.smoking_status || "non-smoker",
    marital_status: user.marital_status || "single",
    num_children: user.num_children || 0
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md transition-all">
      <div className="bg-white rounded-[3rem] w-full max-w-lg shadow-2xl overflow-hidden border border-white ring-1 ring-slate-200 animate-slideUp">
        <div className="px-8 py-6 border-b border-gray-50 flex justify-between items-center bg-slate-50/50">
          <h3 className="font-black text-gray-900 text-lg">Personal Profile</h3>
          <button onClick={onClose} className="w-10 h-10 rounded-full hover:bg-white hover:shadow-sm text-gray-400 text-2xl flex items-center justify-center transition-all">&times;</button>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave(formData); }} className="p-8 space-y-6">
          <div className="grid grid-cols-2 gap-x-6 gap-y-5">
            <div className="col-span-2">
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Full Name</label>
              <input 
                required
                className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none"
                value={formData.name}
                onChange={e => setFormData({...formData, name: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Date of Birth</label>
              <input type="date" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.dob} onChange={e => setFormData({...formData, dob: e.target.value})} />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Gender</label>
              <select className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.gender} onChange={e => setFormData({...formData, gender: e.target.value})}>
                <option value="">Select...</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
                <option value="other">Other</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Smoking Status</label>
              <select className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.smoking_status} onChange={e => setFormData({...formData, smoking_status: e.target.value})}>
                <option value="non-smoker">Non-Smoker</option>
                <option value="smoker">Smoker</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Marital Status</label>
              <select className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.marital_status} onChange={e => setFormData({...formData, marital_status: e.target.value})}>
                <option value="single">Single</option>
                <option value="married">Married</option>
                <option value="divorced">Divorced</option>
                <option value="widowed">Widowed</option>
              </select>
            </div>
            <div className="col-span-2">
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Number of Children</label>
              <input type="number" min="0" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.num_children} onChange={e => setFormData({...formData, num_children: parseInt(e.target.value)})} />
            </div>
          </div>
          <div className="flex gap-4 pt-4">
            <button type="submit" className="flex-1 bg-blue-600 text-white h-14 rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-blue-700 transition-all">Save Profile</button>
            <button type="button" onClick={onClose} className="px-8 h-14 bg-slate-100 text-gray-500 rounded-2xl font-black text-sm uppercase tracking-widest transition-all">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function PolicyModal({ policy, onClose, onSave }) {
  const [formData, setFormData] = useState(policy || {
    insurance_name: "",
    status: "in_effect",
    policy_document_url: "",
    starting_year: new Date().getFullYear(),
    payment_years: 20,
    coverage_years: 99,
    annual_premium: 0,
    coverage_amount: 0
  });

  const [isParsing, setIsParsing] = useState(false);

  const handleFileUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    setIsParsing(true);
    const body = new FormData();
    body.append("file", file);

    try {
      const resp = await fetch("/api/policies/parse", {
        method: "POST",
        body
      });
      const res = await resp.json();
      if (res.success && res.data) {
        const d = res.data;
        setFormData(prev => ({
          ...prev,
          insurance_name: d.insurance_name || prev.insurance_name,
          payment_years: d.payment_years || prev.payment_years,
          coverage_years: d.coverage_years || prev.coverage_years,
          annual_premium: d.annual_premium || prev.annual_premium,
          coverage_amount: d.coverage_amount || prev.coverage_amount,
          policy_document_url: res.document_url || prev.policy_document_url
        }));
      } else {
        alert(res.error || "Failed to parse document");
      }
    } catch (err) {
      alert("Error uploading file");
    } finally {
      setIsParsing(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-md transition-all">
      <div className="bg-white rounded-[3rem] w-full max-w-lg shadow-2xl overflow-hidden border border-white ring-1 ring-slate-200 animate-slideUp">
        <div className="px-8 py-6 border-b border-gray-50 flex justify-between items-center bg-slate-50/50">
          <h3 className="font-black text-gray-900 text-lg">{policy ? "Edit Policy" : "Protect New Asset"}</h3>
          <button onClick={onClose} className="w-10 h-10 rounded-full hover:bg-white hover:shadow-sm text-gray-400 text-2xl flex items-center justify-center transition-all">&times;</button>
        </div>

        <div className="px-8 pt-6">
          <div className={`relative border-2 border-dashed rounded-3xl p-6 transition-all ${isParsing ? 'bg-blue-50 border-blue-200' : 'bg-slate-50 border-slate-200 hover:border-blue-300'}`}>
            <input 
              type="file" 
              className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed" 
              onChange={handleFileUpload}
              disabled={isParsing}
              accept=".pdf"
            />
            <div className="text-center">
              {isParsing ? (
                <div className="flex flex-col items-center">
                  <div className="w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mb-2"></div>
                  <p className="text-xs font-black text-blue-600 uppercase tracking-widest">AI is parsing document...</p>
                </div>
              ) : (
                <>
                  <p className="text-sm font-black text-gray-900 mb-1">Upload Policy Summary</p>
                  <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest text-center">Drag & drop or click to auto-fill details via AI</p>
                </>
              )}
            </div>
          </div>
        </div>
        <form onSubmit={(e) => { e.preventDefault(); onSave(formData); }} className="p-8 space-y-6">
          <div className="grid grid-cols-2 gap-x-6 gap-y-5">
            <div className="col-span-2">
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Policy Identifier</label>
              <input 
                required
                className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold focus:ring-4 focus:ring-blue-50 focus:border-blue-400 outline-none transition-all placeholder:text-gray-300"
                placeholder="e.g. AIA Pro Lifetime Protector"
                value={formData.insurance_name}
                onChange={e => setFormData({...formData, insurance_name: e.target.value})}
              />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Current Status</label>
              <select 
                className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold focus:ring-4 focus:ring-blue-50 focus:border-blue-400 outline-none transition-all"
                value={formData.status}
                onChange={e => setFormData({...formData, status: e.target.value})}
              >
                <option value="in_effect">✓ In Effect</option>
                <option value="lapsed">⚠ Lapsed</option>
                <option value="surrendered">✗ Surrendered</option>
              </select>
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Inception Year</label>
              <input type="number" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.starting_year} onChange={e => setFormData({...formData, starting_year: parseInt(e.target.value)})} />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Pay Term (Y)</label>
              <input type="number" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.payment_years} onChange={e => setFormData({...formData, payment_years: parseInt(e.target.value)})} />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Cover Term (Y)</label>
              <input type="number" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.coverage_years} onChange={e => setFormData({...formData, coverage_years: parseInt(e.target.value)})} />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Annual (S$)</label>
              <input type="number" step="0.01" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.annual_premium} onChange={e => setFormData({...formData, annual_premium: parseFloat(e.target.value)})} />
            </div>
            <div>
              <label className="block text-[10px] font-black text-gray-400 uppercase tracking-widest mb-2">Sum Assured (S$)</label>
              <input type="number" className="w-full px-5 py-3.5 bg-slate-50 border border-slate-100 rounded-2xl text-sm font-bold outline-none" value={formData.coverage_amount} onChange={e => setFormData({...formData, coverage_amount: parseInt(e.target.value)})} />
            </div>
          </div>
          <div className="flex gap-4 pt-4">
            <button type="submit" className="flex-1 bg-blue-600 text-white h-14 rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-blue-700 hover:shadow-xl hover:shadow-blue-200 transition-all">Confirm Data</button>
            <button type="button" onClick={onClose} className="px-8 h-14 bg-slate-100 text-gray-500 rounded-2xl font-black text-sm uppercase tracking-widest hover:bg-slate-200 transition-all">Cancel</button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DashboardView({ user, policies, onAddPolicy, onEditPolicy, onDeletePolicy, onStartAdvice, onLogout }) {
  return (
    <div className="h-full flex flex-col bg-slate-100/50">
      <header className="bg-white border-b border-gray-100 px-10 py-5 flex items-center justify-between shadow-sm z-10 ring-1 ring-slate-100">
        <div className="flex items-center gap-5">
          <div className="w-12 h-12 rounded-3xl bg-blue-600 flex items-center justify-center text-white text-2xl shadow-xl shadow-blue-100 ring-4 ring-blue-50">🛡️</div>
          <div>
            <h1 className="text-xl font-black text-gray-900 tracking-tight leading-none mb-1">Portfolio</h1>
            <p className="text-[11px] font-bold text-gray-400 uppercase tracking-widest">Insurance Management Assistant</p>
          </div>
        </div>
        <div className="flex items-center gap-8">
          <button onClick={onStartAdvice} className="bg-blue-600 text-white px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:bg-blue-700 hover:shadow-xl shadow-lg shadow-blue-100 transition-all active:scale-95 flex items-center gap-2">
            ✨ New Advice
          </button>
          <div className="h-10 w-px bg-slate-100" />
          <div className="flex items-center gap-4">
             <div className="text-right">
               <div className="text-sm font-black text-gray-900 leading-none mb-1">{user.name}</div>
               <div className="flex gap-3 justify-end items-center">
                 <button onClick={() => window.showProfileModal()} className="text-[10px] font-black text-blue-600 hover:text-blue-800 uppercase tracking-widest transition-colors">Edit Profile</button>
                 <span className="text-[10px] text-slate-300">•</span>
                 <button onClick={onLogout} className="text-[10px] font-black text-slate-400 hover:text-red-500 uppercase tracking-widest transition-colors">Sign Out</button>
               </div>
             </div>
             <img src={user.picture} className="w-11 h-11 rounded-3xl border-2 border-white shadow-md shadow-blue-50" />
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-y-auto p-10 max-w-7xl mx-auto w-full">
        <div className="flex items-center justify-between mb-10">
          <h2 className="text-3xl font-black text-gray-950 tracking-tight">Active Coverage</h2>
          <button onClick={() => onAddPolicy()} className="bg-white text-blue-600 border-2 border-blue-50 px-6 py-3 rounded-2xl font-black text-xs uppercase tracking-widest hover:border-blue-200 hover:bg-slate-50 transition-all shadow-sm">
            + Add Asset
          </button>
        </div>

        {policies.length === 0 ? (
          <div className="bg-white rounded-[3rem] p-20 text-center border-4 border-dashed border-slate-100/50 flex flex-col items-center">
            <div className="w-24 h-24 rounded-full bg-slate-50 flex items-center justify-center text-5xl mb-6 grayscale opacity-50">📄</div>
            <h3 className="text-2xl font-black text-gray-900 mb-3">Your portfolio is empty</h3>
            <p className="text-gray-400 text-sm max-w-sm mb-10 font-medium">Record your existing insurance plans here to keep track of premium dates and coverage gaps.</p>
            <button onClick={() => onAddPolicy()} className="bg-blue-600 text-white px-10 py-4 rounded-2xl font-black text-sm uppercase tracking-widest shadow-2xl shadow-blue-100 hover:translate-y-[-2px] transition-all">Add Your First Policy</button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {policies.map(p => (
              <div key={p.id} className="bg-white rounded-[3rem] p-8 border border-gray-50 shadow-sm hover:shadow-2xl hover:shadow-blue-500/5 transition-all duration-500 group relative ring-offset-2 hover:ring-2 ring-blue-100">
                <div className="absolute top-6 right-6 opacity-0 group-hover:opacity-100 transition-all transform translate-y-2 group-hover:translate-y-0 flex gap-2">
                  <button onClick={() => onEditPolicy(p)} className="w-10 h-10 bg-slate-50 rounded-2xl text-slate-400 hover:text-blue-600 hover:bg-blue-50 font-black flex items-center justify-center transition-all">✎</button>
                  <button onClick={() => onDeletePolicy(p.id)} className="w-10 h-10 bg-slate-50 rounded-2xl text-slate-400 hover:text-red-500 hover:bg-red-50 font-black flex items-center justify-center transition-all">&times;</button>
                </div>

                <div className={`text-[10px] inline-flex mb-6 px-3 py-1 rounded-full font-black uppercase tracking-widest border ${
                  p.status === 'in_effect' ? 'bg-green-50 text-green-700 border-green-100' : 
                  p.status === 'lapsed' ? 'bg-amber-50 text-amber-700 border-amber-100' : 'bg-red-50 text-red-700 border-red-100'
                }`}>
                  {p.status.replace('_', ' ')}
                </div>

                <h3 className="text-xl font-black text-gray-900 mb-8 leading-tight line-clamp-2 min-h-[3rem]">{p.insurance_name}</h3>

                <div className="grid grid-cols-2 gap-8 mb-8">
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1.5">Sum Assured</div>
                    <div className="text-lg font-black text-gray-900">S$ {p.coverage_amount.toLocaleString()}</div>
                    <div className="text-[9px] font-bold text-gray-400 mt-2 uppercase">Until {p.starting_year + p.coverage_years}</div>
                  </div>
                  <div>
                    <div className="text-[10px] font-black text-gray-400 uppercase tracking-widest mb-1.5">Premium</div>
                    <div className="text-lg font-black text-blue-600">S$ {p.annual_premium.toLocaleString()}</div>
                    <div className="text-[9px] font-bold text-gray-400 mt-2 uppercase">{p.payment_years}y Tenure</div>
                  </div>
                </div>

                {p.policy_document_url && (
                  <div className="pt-6 border-t border-slate-50">
                    <a href={p.policy_document_url} target="_blank" className="text-[11px] font-black text-blue-600 uppercase tracking-widest flex items-center gap-2 hover:translate-x-1 transition-transform">
                      <span>📄</span> View Document &rarr;
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

// ─── Main Controller ─────────────────────────────────────────────────────────

function App() {
  const [user, setUser] = useState(null);
  const [view, setView] = useState("dashboard");
  const [policies, setPolicies] = useState([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(null);
  const [profileModal, setProfileModal] = useState(false);

  // Expose to dashboard header
  window.showProfileModal = () => setProfileModal(true);

  const [consultantData, setConsultantData] = useState({
    sessionId: null, messages: [], phase: "idle", isWaiting: false, isTyping: false,
    requirements: null, criteria: null, policies: [], activeTab: "requirements"
  });

  const wsRef = useRef(null);

  useEffect(() => { fetchUser(); }, []);

  const fetchUser = async () => {
    try {
      const resp = await fetch("/api/auth/me");
      const data = await resp.json();
      if (data.logged_in) {
        setUser(data.user);
        fetchPolicies();
      }
    } catch (e) {} finally { setLoading(false); }
  };

  const fetchPolicies = async () => {
    try {
      const resp = await fetch("/api/policies");
      const data = await resp.json();
      setPolicies(data.policies || []);
    } catch (e) {}
  };

  const savePolicy = async (data) => {
    const isEdit = !!data.id;
    const resp = await fetch(isEdit ? `/api/policies/${data.id}` : "/api/policies", {
      method: isEdit ? "PUT" : "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (resp.ok) { setModal(null); fetchPolicies(); }
  };

  const saveProfile = async (data) => {
    const resp = await fetch("/api/auth/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (resp.ok) {
      const res = await resp.json();
      setUser(res.user);
      setProfileModal(false);
    }
  };

  const deletePolicy = async (id) => {
    if (confirm("Permanently remove this record?")) {
      await fetch(`/api/policies/${id}`, { method: "DELETE" });
      fetchPolicies();
    }
  };

  const handleConsultantMsg = (raw) => {
    const d = JSON.parse(raw);
    setConsultantData(prev => {
      const next = { ...prev };
      switch (d.type) {
        case "question": next.isTyping = false; next.messages = [...next.messages, mkMsg("agent", d.content)]; next.isWaiting = true; break;
        case "status": if (d.phase) next.phase = d.phase; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("status", d.message, d.phase)]; break;
        case "requirements": next.requirements = d.data; next.activeTab = "requirements"; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("milestone", "Profile captured")]; break;
        case "criteria": next.criteria = d.data; next.activeTab = "criteria"; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("milestone", "Criteria generated")]; break;
        case "policies": next.policies = d.data; next.activeTab = "policies"; next.messages = [...next.messages.filter(m => m.type !== "status"), mkMsg("milestone", "Evaluations complete")]; break;
        case "complete": next.phase = "complete"; break;
      }
      return next;
    });
  };

  const handleSend = async (text) => {
    setConsultantData(prev => ({...prev, messages: [...prev.messages, mkMsg("user", text)]}));
    if (!consultantData.sessionId) {
      const resp = await fetch("/api/sessions", { method: "POST" });
      const { session_id } = await resp.json();
      setConsultantData(prev => ({...prev, sessionId: session_id}));
      const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${window.location.host}/ws/${session_id}`);
      wsRef.current = ws;
      ws.onopen = () => { setConsultantData(prev => ({...prev, isTyping: true})); ws.send(JSON.stringify({ type: "start", message: text })); };
      ws.onmessage = (e) => handleConsultantMsg(e.data);
    } else {
      setConsultantData(prev => ({...prev, isWaiting: false, isTyping: true}));
      wsRef.current?.send(JSON.stringify({ type: "answer", content: text }));
    }
  };

  if (loading) return (
    <div className="h-screen flex items-center justify-center bg-slate-50">
      <div className="w-12 h-12 border-4 border-blue-600 border-t-transparent rounded-full animate-spin shadow-xl"></div>
    </div>
  );

  if (!user) return (
    <div className="h-screen flex items-center justify-center bg-slate-100 p-8">
      <div className="bg-white p-14 rounded-[4rem] shadow-2xl max-w-sm w-full text-center border border-white ring-1 ring-slate-200">
        <div className="w-24 h-24 rounded-[3rem] bg-blue-600 flex items-center justify-center text-white text-5xl mx-auto mb-10 shadow-2xl shadow-blue-100 ring-8 ring-blue-50 transition-transform hover:scale-110">🛡️</div>
        <h1 className="text-3xl font-black text-gray-950 mb-4 tracking-tighter">Insurance Central</h1>
        <p className="text-slate-400 text-sm mb-12 font-bold uppercase tracking-widest leading-relaxed">Secure. Smart. AI-Powered.</p>
        <a href="/api/auth/login" className="block w-full bg-blue-600 text-white py-5 rounded-3xl font-black hover:bg-black hover:shadow-2xl transition-all uppercase tracking-widest text-xs shadow-xl shadow-blue-100">
          Connect Google Account
        </a>
      </div>
    </div>
  );

  if (view === "consultant") return (
    <div className="h-screen flex flex-col bg-slate-50/50">
      <header className="bg-white border-b border-gray-100 px-10 py-5 flex items-center justify-between shadow-sm z-10 transition-all">
        <div className="flex items-center gap-6">
          <button onClick={() => setView("dashboard")} className="w-10 h-10 rounded-2xl bg-slate-50 text-gray-400 hover:bg-slate-100 hover:text-gray-950 flex items-center justify-center transition-all">←</button>
          <div>
            <h1 className="font-black text-gray-950 text-base tracking-tight leading-none mb-1">Expert Advice</h1>
            <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest">Consultation Session</p>
          </div>
        </div>
        <PhaseBar phase={consultantData.phase} />
      </header>
      <div className="flex-1 flex overflow-hidden">
        <div className="w-1/2 border-r border-slate-100 flex flex-col shadow-2xl shadow-slate-200/50 z-10">
          <ChatPanel 
             messages={consultantData.messages} isWaitingAnswer={consultantData.isWaiting}
             isTyping={consultantData.isTyping} phase={consultantData.phase}
             onSend={handleSend} isStarted={!!consultantData.sessionId}
          />
        </div>
        <div className="flex-1 overflow-hidden flex flex-col bg-white/50 backdrop-blur-3xl">
           <div className="bg-white border-b border-slate-50 flex gap-1 px-8 pt-5">
              {['requirements', 'criteria', 'policies'].map(t => (
                <button 
                  key={t} onClick={() => setConsultantData(prev => ({...prev, activeTab: t}))}
                  className={`px-6 py-3 text-[10px] font-black uppercase tracking-widest rounded-t-2xl transition-all ${consultantData.activeTab === t ? 'bg-slate-50 text-blue-600 border-b-4 border-blue-600' : 'text-gray-400 hover:text-gray-600'}`}
                >
                  {t}
                </button>
              ))}
           </div>
           <div className="flex-1 overflow-hidden">
             {consultantData.activeTab === 'requirements' && <RequirementsView data={consultantData.requirements} />}
             {consultantData.activeTab === 'criteria' && <CriteriaView data={consultantData.criteria} />}
             {consultantData.activeTab === 'policies' && <PoliciesView data={consultantData.policies} />}
           </div>
        </div>
      </div>
    </div>
  );

  return (
    <div className="h-screen w-full relative overflow-hidden">
      <DashboardView 
        user={user} policies={policies} 
        onAddPolicy={() => setModal({})} onEditPolicy={(p) => setModal(p)}
        onDeletePolicy={deletePolicy} onStartAdvice={() => setView("consultant")}
        onLogout={() => window.location.href = "/api/auth/logout"}
      />
      {modal && <PolicyModal policy={modal.id ? modal : null} onClose={() => setModal(null)} onSave={savePolicy} />}
      {profileModal && <ProfileModal user={user} onClose={() => setProfileModal(false)} onSave={saveProfile} />}
    </div>
  );
}

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(<App />);
