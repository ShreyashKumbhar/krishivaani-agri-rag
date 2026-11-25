import { useEffect, useMemo, useRef, useState } from 'react';
import {
  ArrowRight,
  AudioLines,
  BadgeCheck,
  BookOpenText,
  ChevronDown,
  ChevronUp,
  CircleHelp,
  CloudSun,
  Crop,
  Database,
  Ear,
  Info,
  Loader2,
  MapPin,
  Mic,
  MicOff,
  Pause,
  Play,
  Send,
  Sparkles,
  Store,
  ThumbsDown,
  ThumbsUp,
  Volume2,
  Waves,
} from 'lucide-react';
import { api, formatDate, titleCase } from '../api.js';
import { useApp } from '../App.jsx';
import {
  Badge,
  ConfidenceMeter,
  DataModeBadge,
  DecisionBadge,
  SourceCard,
  Spinner,
} from '../components/ui.jsx';

const LANGUAGES = [
  { code: 'hi', label: 'हिंदी', english: 'Hindi', speech: 'hi-IN' },
  { code: 'mr', label: 'मराठी', english: 'Marathi', speech: 'mr-IN' },
  { code: 'en', label: 'English', english: 'English', speech: 'en-IN' },
];

const DECISION_COPY = {
  answer: 'Answer grounded in approved evidence',
  ask_to_repeat: 'The assistant needs one more detail',
  refuse: 'The safety gate stopped this answer',
};

export default function Assistant() {
  const { config } = useApp();
  const [language, setLanguage] = useState('hi');
  const [text, setText] = useState('');
  const [crop, setCrop] = useState('');
  const [district, setDistrict] = useState('');
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [listening, setListening] = useState(false);
  const [voiceSupported, setVoiceSupported] = useState(true);
  const [voiceNote, setVoiceNote] = useState('');
  const [feedbackSent, setFeedbackSent] = useState('');
  const [playing, setPlaying] = useState(false);
  const [audioNote, setAudioNote] = useState('');
  const [showDetails, setShowDetails] = useState(false);
  const [session, setSession] = useState([]);
  const recognitionRef = useRef(null);
  const audioRef = useRef(null);

  const samples = config?.sample_questions?.[language] || [];
  const crops = config?.crops || [];
  const districts = config?.districts || [];
  const speechLang = LANGUAGES.find((item) => item.code === language)?.speech || 'hi-IN';

  useEffect(() => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceSupported(false);
      setVoiceNote('This browser does not expose the Web Speech API. Type the question or use Chrome/Edge for microphone input.');
    }
    return () => {
      recognitionRef.current?.stop?.();
      audioRef.current?.pause?.();
      window.speechSynthesis?.cancel?.();
    };
  }, []);

  const sampleQuestions = useMemo(() => samples.slice(0, 4), [samples]);

  async function runQuery(question = text, inputMode = 'text', asrConfidence = null) {
    const value = question.trim();
    if (value.length < 2 || loading) return;
    setLoading(true);
    setError('');
    setFeedbackSent('');
    setAudioNote('');
    setShowDetails(false);
    window.speechSynthesis?.cancel?.();
    audioRef.current?.pause?.();
    try {
      const result = await api.ask({
        text: value,
        language,
        crop: crop || null,
        district: district || null,
        state: 'Maharashtra',
        input_mode: inputMode,
        asr_confidence: asrConfidence,
      });
      setResponse(result);
      setSession((items) => [result, ...items].slice(0, 5));
    } catch (err) {
      setError(err.message || 'The assistant could not complete this request.');
    } finally {
      setLoading(false);
    }
  }

  function startListening() {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setVoiceSupported(false);
      setVoiceNote('Microphone recognition is not supported in this browser. Type the question instead.');
      return;
    }
    if (listening) {
      recognitionRef.current?.stop?.();
      setListening(false);
      return;
    }
    const recognition = new SpeechRecognition();
    recognition.lang = speechLang;
    recognition.interimResults = true;
    recognition.continuous = false;
    recognition.maxAlternatives = 1;
    recognitionRef.current = recognition;
    setVoiceNote('');
    setListening(true);
    recognition.onresult = (event) => {
      let transcript = '';
      let confidence = null;
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        transcript += event.results[index][0].transcript;
        if (event.results[index].isFinal) confidence = event.results[index][0].confidence;
      }
      setText(transcript.trim());
      if (event.results[event.results.length - 1].isFinal && transcript.trim().length > 1) {
        runQuery(transcript.trim(), 'voice_browser', confidence);
      }
    };
    recognition.onerror = (event) => {
      setListening(false);
      if (event.error === 'not-allowed') {
        setVoiceNote('Microphone permission was denied. Allow microphone access or type the question.');
      } else if (event.error === 'no-speech') {
        setVoiceNote('No speech was detected. Try again or type the question.');
      } else {
        setVoiceNote(`Speech recognition stopped (${event.error}). You can type the question instead.`);
      }
    };
    recognition.onend = () => setListening(false);
    try {
      recognition.start();
    } catch {
      setListening(false);
      setVoiceNote('Could not start the microphone. Try again.');
    }
  }

  async function playAnswer() {
    if (!response?.answer) return;
    if (playing) {
      audioRef.current?.pause?.();
      window.speechSynthesis?.cancel?.();
      setPlaying(false);
      return;
    }
    setAudioNote('');
    setPlaying(true);
    try {
      const blob = await api.synthesize(response.answer, response.language);
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => {
        setPlaying(false);
        URL.revokeObjectURL(url);
      };
      audio.onerror = () => {
        setPlaying(false);
        URL.revokeObjectURL(url);
      };
      await audio.play();
    } catch (err) {
      // Browser speech synthesis is the documented fallback when edge-tts is
      // unavailable (offline, blocked network or TTS_PROVIDER=browser).
      const utterance = new SpeechSynthesisUtterance(response.answer);
      utterance.lang = response.language === 'mr' ? 'mr-IN' : response.language === 'hi' ? 'hi-IN' : 'en-IN';
      utterance.rate = 0.92;
      utterance.onend = () => setPlaying(false);
      utterance.onerror = () => setPlaying(false);
      window.speechSynthesis.speak(utterance);
      setAudioNote(`Server TTS unavailable (${err.message}). Using the browser voice fallback.`);
    }
  }

  async function sendFeedback(rating) {
    if (!response || feedbackSent) return;
    try {
      await api.feedback({ query_id: response.query_id, rating, comment: '' });
      setFeedbackSent(rating);
    } catch (err) {
      setAudioNote(`Feedback could not be saved: ${err.message}`);
    }
  }

  function chooseSample(question) {
    setText(question);
    runQuery(question);
  }

  const showClarify = response && response.decision !== 'answer';
  const trimmed = text.trim();
  const hasDevanagari = /[\u0900-\u097F]/.test(trimmed);
  const looksEnglish = trimmed.length >= 10 && !hasDevanagari && /\b(what|why|how|when|which|will|is|are|my|the|for|in)\b/i.test(trimmed);
  const langHint =
    language === 'en' && hasDevanagari
      ? { code: 'hi', label: 'Devanagari text detected — switch to हिंदी or मराठी?' }
      : language !== 'en' && looksEnglish
        ? { code: 'en', label: 'English text detected — switch to English?' }
        : null;

  return (
    <div className="assistant-page">
      <section className="hero">
        <div className="hero-copy">
          <div className="eyebrow"><Waves size={14} /> Voice-first · Hindi · Marathi · English</div>
          <h1>Ask your farming question.<br /><span>Listen to a grounded answer.</span></h1>
          <p>
            KrishiVaani combines multilingual retrieval, agricultural terminology, live weather and mandi tools
            with a conservative safety gate. It cites what it uses and refuses when the evidence is weak.
          </p>
          <div className="hero-badges">
            <Badge tone="green" dot>Grounded answers</Badge>
            <Badge tone="neutral">Hybrid retrieval</Badge>
            <Badge tone="amber">Demo knowledge base</Badge>
          </div>
        </div>
        <div className="hero-panel">
          <div className="hero-panel-title"><AudioLines size={16} /> Voice pipeline</div>
          <div className="pipeline">
            <div><Ear size={16} /><span>Speech</span></div>
            <ArrowRight size={14} />
            <div><Sparkles size={16} /><span>Understand</span></div>
            <ArrowRight size={14} />
            <div><BookOpenText size={16} /><span>Retrieve</span></div>
            <ArrowRight size={14} />
            <div><Volume2 size={16} /><span>Speak</span></div>
          </div>
          <div className="hero-panel-note">
            Browser ASR by default. Server TTS with an automatic browser voice fallback.
          </div>
        </div>
      </section>

      <section className="composer-card">
        <div className="composer-top">
          <div className="language-switch" role="tablist" aria-label="Answer language">
            {LANGUAGES.map((item) => (
              <button
                key={item.code}
                type="button"
                role="tab"
                aria-selected={language === item.code}
                className={language === item.code ? 'lang-active' : ''}
                onClick={() => setLanguage(item.code)}
              >
                <span>{item.label}</span>
                <small>{item.english}</small>
              </button>
            ))}
          </div>
          <div className="composer-providers">
            <Badge tone="neutral"><Database size={12} /> {config?.providers?.embedding?.provider || 'hashed'}</Badge>
            <Badge tone={config?.providers?.llm?.available ? 'green' : 'amber'}>
              {config?.providers?.llm?.available ? 'LLM configured' : 'No LLM · extractive'}
            </Badge>
          </div>
        </div>

        <div className="composer-input-wrap">
          <textarea
            value={text}
            onChange={(event) => setText(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter' && !event.shiftKey) {
                event.preventDefault();
                runQuery();
              }
            }}
            placeholder={
              language === 'hi'
                ? 'अपना सवाल लिखें या माइक दबाकर बोलें… जैसे: मेरी कपास की पत्तियाँ पीली क्यों हो रही हैं?'
                : language === 'mr'
                  ? 'तुमचा प्रश्न लिहा किंवा माइक दाबून बोला… उदा.: माझ्या कापसाची पाने पिवळी का होत आहेत?'
                  : 'Type your question or press the mic and speak… e.g. Why are my cotton leaves turning yellow?'
            }
            rows={3}
          />
          <div className="composer-actions">
            <button
              type="button"
              className={`mic-button ${listening ? 'mic-live' : ''}`}
              onClick={startListening}
              disabled={!voiceSupported}
              title={voiceSupported ? 'Speak your question' : 'Microphone not supported in this browser'}
            >
              {listening ? <MicOff size={20} /> : <Mic size={20} />}
              <span>{listening ? 'Listening…' : 'Speak'}</span>
            </button>
            <button type="button" className="button button-primary send-button" onClick={() => runQuery()} disabled={loading || text.trim().length < 2}>
              {loading ? <Loader2 className="spin" size={18} /> : <Send size={17} />}
              {loading ? 'Thinking…' : 'Get answer'}
            </button>
          </div>
        </div>

        {listening ? (
          <div className="listening-strip">
            <span className="pulse-dot" /> Listening in {LANGUAGES.find((item) => item.code === language)?.english}. Speak clearly; the transcript will be sent automatically.
          </div>
        ) : null}
        {voiceNote ? <div className="inline-note"><Info size={15} /> {voiceNote}</div> : null}
        {langHint ? (
          <div className="inline-note">
            <Info size={15} /> {langHint.label}{' '}
            <button type="button" className="text-link" onClick={() => setLanguage(langHint.code)}>
              Switch to {langHint.code === 'en' ? 'English' : 'हिंदी'}
            </button>
            {langHint.code === 'hi' ? (
              <>
                {' · '}
                <button type="button" className="text-link" onClick={() => setLanguage('mr')}>
                  मराठी
                </button>
              </>
            ) : null}
          </div>
        ) : null}

        <div className="composer-meta">
          <label>
            <Crop size={14} /> Crop
            <select value={crop} onChange={(event) => setCrop(event.target.value)}>
              <option value="">Auto-detect</option>
              {crops.map((item) => <option key={item} value={item}>{titleCase(item)}</option>)}
            </select>
          </label>
          <label>
            <MapPin size={14} /> District
            <select value={district} onChange={(event) => setDistrict(event.target.value)}>
              <option value="">Auto-detect / Nashik</option>
              {districts.map((item) => <option key={item} value={item}>{item}</option>)}
            </select>
          </label>
          <span className="composer-hint">Enter to send · Shift+Enter for a new line</span>
        </div>

        <div className="samples">
          <span className="samples-label">Try a sample</span>
          {sampleQuestions.map((question) => (
            <button key={question} type="button" className="sample-chip" onClick={() => chooseSample(question)}>
              {question}
            </button>
          ))}
        </div>
      </section>

      {error ? <div className="alert alert-error"><Info size={17} /> {error}</div> : null}

      {loading ? (
        <section className="answer-card answer-loading">
          <Spinner label="Understanding the question, retrieving evidence and checking the safety gate…" />
          <div className="skeleton-lines"><span /><span /><span /></div>
        </section>
      ) : null}

      {response && !loading ? (
        <section className={`answer-card decision-${response.decision}`}>
          <div className="answer-head">
            <div className="answer-head-left">
              <DecisionBadge decision={response.decision} />
              <Badge tone="neutral">{titleCase(response.intent)}</Badge>
              <Badge tone="neutral">{response.language_name}</Badge>
              {response.simulated ? <Badge tone="amber" dot>Tool data simulated</Badge> : null}
              {response.demo_knowledge ? <Badge tone="amber">Demo corpus</Badge> : null}
            </div>
            <div className="answer-head-right">
              <span className="latency">{response.latency_ms?.toFixed(0)} ms</span>
              <button type="button" className={`audio-button ${playing ? 'audio-playing' : ''}`} onClick={playAnswer}>
                {playing ? <Pause size={16} /> : <Play size={16} />}
                {playing ? 'Stop' : 'Listen'}
              </button>
            </div>
          </div>

          <div className="answer-grid">
            <div className="answer-main">
              <div className="answer-question">
                <span>You asked</span>
                <p>{response.text}</p>
              </div>
              <div className="answer-text">{response.answer}</div>
              {response.safety_note ? (
                <div className="safety-callout"><ShieldIcon /> <span>{response.safety_note}</span></div>
              ) : null}
              {audioNote ? <div className="inline-note"><Info size={15} /> {audioNote}</div> : null}
              {showClarify ? (
                <div className="clarify-callout">
                  <CircleHelp size={18} />
                  <div>
                    <strong>{DECISION_COPY[response.decision]}</strong>
                    <p>{response.reason_detail}</p>
                  </div>
                </div>
              ) : null}

              <div className="answer-toolbar">
                <div className="feedback">
                  <span>Was this useful?</span>
                  <button
                    type="button"
                    className={feedbackSent === 'up' ? 'feedback-active' : ''}
                    onClick={() => sendFeedback('up')}
                    disabled={Boolean(feedbackSent)}
                  >
                    <ThumbsUp size={15} /> Yes
                  </button>
                  <button
                    type="button"
                    className={feedbackSent === 'down' ? 'feedback-active' : ''}
                    onClick={() => sendFeedback('down')}
                    disabled={Boolean(feedbackSent)}
                  >
                    <ThumbsDown size={15} /> Not really
                  </button>
                  {feedbackSent ? <small>Saved to the review queue.</small> : null}
                </div>
                <button type="button" className="text-button" onClick={() => setShowDetails((value) => !value)}>
                  {showDetails ? <ChevronUp size={15} /> : <ChevronDown size={15} />}
                  {showDetails ? 'Hide provenance' : 'Show provenance'}
                </button>
              </div>
            </div>

            <aside className="answer-aside">
              <ConfidenceMeter value={response.confidence} />
              <div className="mini-grid">
                <div><span>Intent</span><strong>{titleCase(response.intent)}</strong></div>
                <div><span>Intent conf.</span><strong>{Math.round((response.intent_confidence || 0) * 100)}%</strong></div>
                <div><span>Evidence</span><strong>{response.evidence?.length || 0} passages</strong></div>
                <div><span>Grounding</span><strong>{Math.round((response.grounding_score || 0) * 100)}%</strong></div>
              </div>
              <div className="reason-box">
                <span>Gate reason</span>
                <strong>{titleCase(response.reason_code)}</strong>
                <p>{response.reason_detail}</p>
              </div>
              {response.entities?.crop || response.entities?.district ? (
                <div className="entity-row">
                  {response.entities?.crop ? <Badge tone="green"><Crop size={12} /> {titleCase(response.entities.crop)}</Badge> : null}
                  {response.entities?.district ? <Badge tone="neutral"><MapPin size={12} /> {response.entities.district}</Badge> : null}
                </div>
              ) : null}
            </aside>
          </div>

          {response.tool_data ? <ToolResult response={response} /> : null}

          {response.citations?.length ? (
            <div className="citations-block">
              <div className="block-title"><BookOpenText size={17} /> Sources used <span>{response.citations.length}</span></div>
              <div className="source-list">
                {response.citations.map((citation, index) => <SourceCard key={`${citation.document_id}-${index}`} citation={citation} index={index} />)}
              </div>
            </div>
          ) : null}

          {showDetails ? (
            <div className="provenance-block">
              <div className="provenance-grid">
                <div><span>Answer source</span><strong>{titleCase(response.provenance?.answer_source)}</strong></div>
                <div><span>Generation</span><strong>{response.generation_provider}</strong></div>
                <div><span>Embedding</span><strong>{response.provenance?.embedding_provider}</strong></div>
                <div><span>Knowledge mode</span><strong>{titleCase(response.provenance?.knowledge_mode)}</strong></div>
                <div><span>Tool mode</span><strong>{response.provenance?.tool_mode ? response.provenance.tool_mode.toUpperCase() : '—'}</strong></div>
                <div><span>Logged at</span><strong>{formatDate(response.created_at)}</strong></div>
              </div>
              {response.evidence?.length ? (
                <div className="evidence-list">
                  {response.evidence.map((item, index) => (
                    <details key={item.chunk_id} open={index === 0}>
                      <summary>
                        <span>{index + 1}. {item.title}</span>
                        <span className="evidence-score">score {Number(item.score).toFixed(3)}</span>
                      </summary>
                      <p>{item.text}</p>
                      <div className="evidence-meta">
                        <Badge tone="neutral">{item.language?.toUpperCase()}</Badge>
                        <Badge tone="neutral">{titleCase(item.category)}</Badge>
                        <span>{item.publisher}</span>
                      </div>
                    </details>
                  ))}
                </div>
              ) : null}
              {response.signals ? (
                <div className="signals">
                  {Object.entries(response.signals).filter(([, value]) => value !== null && value !== undefined).map(([key, value]) => (
                    <div key={key}><span>{titleCase(key)}</span><strong>{typeof value === 'number' ? Number(value).toFixed(3) : String(value)}</strong></div>
                  ))}
                </div>
              ) : null}
              <div className="disclaimer-line"><Info size={14} /> {response.disclaimer}</div>
            </div>
          ) : null}

          {response.suggested_followups?.length ? (
            <div className="followups">
              <span>Follow-up questions</span>
              {response.suggested_followups.map((question) => (
                <button key={question} type="button" onClick={() => chooseSample(question)}>{question} <ArrowRight size={13} /></button>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}

      {session.length > 1 ? (
        <section className="session-strip">
          <div className="block-title"><HistoryIcon /> This session</div>
          <div className="session-list">
            {session.slice(1).map((item) => (
              <button key={item.query_id} type="button" onClick={() => { setResponse(item); setText(item.text); }}>
                <DecisionBadge decision={item.decision} />
                <span>{item.text}</span>
                <small>{item.latency_ms?.toFixed(0)} ms</small>
              </button>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function ShieldIcon() {
  return <BadgeCheck size={17} />;
}

function HistoryIcon() {
  return <Waves size={16} />;
}

function ToolResult({ response }) {
  const data = response.tool_data;
  const isMandi = response.intent === 'market_price';
  const labels = data.commodity_labels || {};
  const commodity = labels[response.language] || labels.en || data.commodity;
  return (
    <div className="tool-card">
      <div className="tool-card-head">
        <div className="tool-icon">{isMandi ? <Store size={20} /> : <CloudSun size={20} />}</div>
        <div>
          <strong>{isMandi ? 'Mandi price record' : 'Weather forecast record'}</strong>
          <span>{data.provider || data.source_name}</span>
        </div>
        <DataModeBadge mode={data.data_mode} />
      </div>
      {isMandi ? (
        <div className="tool-values">
          <div><span>Commodity</span><strong>{commodity}</strong></div>
          <div><span>Market</span><strong>{data.market_labels?.[response.language] || data.market}</strong></div>
          <div><span>Modal price</span><strong>₹{Number(data.modal_price_inr_per_quintal || 0).toLocaleString('en-IN')}/qtl</strong></div>
          <div><span>Range</span><strong>₹{Number(data.min_price_inr_per_quintal || 0).toLocaleString('en-IN')} – ₹{Number(data.max_price_inr_per_quintal || 0).toLocaleString('en-IN')}</strong></div>
        </div>
      ) : (
        <div className="tool-values">
          <div className="tool-summary"><span>Summary</span><strong>{data.summary?.[response.language] || data.summary?.en}</strong></div>
          <div><span>Data as of</span><strong>{data.data_as_of || '—'}</strong></div>
          <div><span>Provider</span><strong>{data.provider}</strong></div>
        </div>
      )}
      <div className="tool-note"><Info size={14} /> {data.provenance_note}</div>
    </div>
  );
}
