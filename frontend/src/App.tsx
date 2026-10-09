import { useEffect, useMemo, useRef, useState } from "react";
import {
  Clip,
  Job,
  Settings,
  defaultSettings,
  fetchJob,
  startSample,
  uploadVideo,
} from "./api";

const STORAGE_KEY = "spool-job";

const STEPS = [
  { id: "queued", label: "Ingest" },
  { id: "transcribing", label: "Transcribe" },
  { id: "highlighting", label: "Find hooks" },
  { id: "rendering", label: "Cut & caption" },
];

const MOOD_TONE: Record<string, string> = {
  funny: "bg-amber-200/15 text-amber-100",
  dramatic: "bg-coral/15 text-orange-200",
  informative: "bg-sky-200/10 text-sky-100",
  hype: "bg-lime/15 text-lime",
  emotional: "bg-rose-200/10 text-rose-100",
  inspiring: "bg-emerald-200/10 text-emerald-100",
};

export default function App() {
  const [settings, setSettings] = useState<Settings>(defaultSettings);
  const [job, setJob] = useState<Job | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const [upload, setUpload] = useState<number | null>(null);
  const [pending, setPending] = useState<string | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const saved = sessionStorage.getItem(STORAGE_KEY);
    if (!saved) return;
    fetchJob(saved)
      .then(setJob)
      .catch(() => sessionStorage.removeItem(STORAGE_KEY));
  }, []);

  useEffect(() => {
    if (!job || job.stage === "done" || job.stage === "error") return;
    const timer = window.setInterval(() => {
      fetchJob(job.id)
        .then(setJob)
        .catch((error: Error) => setBanner(error.message));
    }, 800);
    return () => window.clearInterval(timer);
  }, [job]);

  const busy = pending !== null || (!!job && job.stage !== "done" && job.stage !== "error");
  const lengthProblem = lengthError(settings);

  function remember(next: Job) {
    sessionStorage.setItem(STORAGE_KEY, next.id);
    setJob(next);
    setBanner(null);
  }

  async function onFile(file: File) {
    if (!file || busy) return;
    if (lengthProblem) {
      setBanner(lengthProblem);
      return;
    }
    setPending("Uploading");
    setUpload(0);
    setBanner(null);
    try {
      const created = await uploadVideo(file, settings, setUpload);
      remember(created);
    } catch (error) {
      setBanner(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setPending(null);
      setUpload(null);
    }
  }

  async function onSample() {
    if (lengthProblem) {
      setBanner(lengthProblem);
      return;
    }
    setBanner(null);
    setPending("Building the sample reel");
    try {
      const created = await startSample(settings);
      remember(created);
    } catch (error) {
      setBanner(error instanceof Error ? error.message : "Sample failed.");
    } finally {
      setPending(null);
    }
  }

  function reset() {
    sessionStorage.removeItem(STORAGE_KEY);
    setJob(null);
    setBanner(null);
  }

  return (
    <div className="mx-auto min-h-screen max-w-6xl px-4 pb-16 pt-6 sm:px-6">
      <header className="mb-8 flex items-end justify-between gap-4">
        <div>
          <p className="font-display text-4xl italic tracking-tight text-ink sm:text-5xl">Spool</p>
          <p className="mt-1 max-w-md text-sm text-mute sm:text-base">
            Long video in. Vertical hooks out. Transcription stays on this machine.
          </p>
        </div>
        <span className="hidden rounded-full border border-line px-3 py-1 text-xs uppercase tracking-[0.16em] text-mute sm:inline">
          Local transcription
        </span>
      </header>

      {banner && (
        <p className="mb-4 rounded-2xl border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-orange-100">
          {banner}
        </p>
      )}

      {(!job || job.stage === "error") && (
        <Dropzone
          dragOver={dragOver}
          upload={upload}
          pending={pending}
          busy={busy || lengthProblem !== null}
          onBrowse={() => inputRef.current?.click()}
          onSample={onSample}
          onDrag={(over) => setDragOver(over)}
          onFile={onFile}
        />
      )}
      <input
        ref={inputRef}
        type="file"
        accept="video/*,.mp4,.mov,.mkv,.webm,.m4v"
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) void onFile(file);
          event.target.value = "";
        }}
      />

      {(!job || job.stage === "error") && (
        <SettingsBar
          settings={settings}
          onChange={setSettings}
          disabled={busy}
          problem={lengthProblem}
        />
      )}

      {job && job.stage !== "done" && job.stage !== "error" && (
        <ProgressPanel job={job} />
      )}

      {job?.stage === "error" && job.error && (
        <p className="mt-4 rounded-2xl border border-coral/40 bg-coral/10 px-4 py-3 text-sm text-orange-100">
          {job.error}
        </p>
      )}

      {job?.stage === "done" && (
        <Gallery job={job} onReset={reset} />
      )}
    </div>
  );
}

function Dropzone({
  dragOver,
  upload,
  pending,
  busy,
  onBrowse,
  onSample,
  onDrag,
  onFile,
}: {
  dragOver: boolean;
  upload: number | null;
  pending: string | null;
  busy: boolean;
  onBrowse: () => void;
  onSample: () => void;
  onDrag: (over: boolean) => void;
  onFile: (file: File) => void;
}) {
  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        onDrag(true);
      }}
      onDragLeave={() => onDrag(false)}
      onDrop={(event) => {
        event.preventDefault();
        onDrag(false);
        const file = event.dataTransfer.files?.[0];
        if (file) onFile(file);
      }}
      className={`rounded-[28px] border px-6 py-12 text-center transition sm:px-10 ${
        dragOver ? "border-lime bg-lime/10" : "border-line bg-panel/80"
      }`}
    >
      <p className="font-display text-3xl italic text-ink sm:text-4xl">Drop a long video</p>
      <p className="mx-auto mt-3 max-w-lg text-sm leading-relaxed text-mute sm:text-base">
        Talking-head episodes, lectures, podcasts. An hour is fine. Spool transcribes locally,
        keeps the lines that could stop a scroll, and hands you 9:16 clips.
      </p>
      <div className="mt-6 flex flex-col items-center justify-center gap-3 sm:flex-row">
        <button
          type="button"
          disabled={busy}
          onClick={onBrowse}
          className="rounded-full bg-lime px-5 py-2.5 text-sm font-medium text-paper disabled:opacity-50"
        >
          {pending === "Uploading"
            ? `Uploading ${Math.round((upload ?? 0) * 100)}%`
            : pending ?? "Choose a file"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onSample}
          className="rounded-full border border-line px-5 py-2.5 text-sm text-ink disabled:opacity-50"
        >
          Cut the sample reel
        </button>
      </div>
    </div>
  );
}

function lengthError({ min_len, max_len }: Settings): string | null {
  if (!(min_len >= 5 && min_len <= 90)) return "Shortest must be between 5 and 90 seconds.";
  if (!(max_len >= 8 && max_len <= 120)) return "Longest must be between 8 and 120 seconds.";
  if (min_len >= max_len) return "Shortest must be less than longest.";
  return null;
}

function SettingsBar({
  settings,
  onChange,
  disabled,
  problem,
}: {
  settings: Settings;
  onChange: (next: Settings) => void;
  disabled: boolean;
  problem: string | null;
}) {
  const patch = (partial: Partial<Settings>) => onChange({ ...settings, ...partial });
  return (
    <section className="mt-5 rounded-[28px] border border-line bg-panel/60 p-4 sm:p-5">
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <label className="block text-xs uppercase tracking-[0.14em] text-mute">
          Clips · {settings.clip_count}
          <input
            className="mt-2 w-full accent-lime"
            type="range"
            min={1}
            max={8}
            disabled={disabled}
            value={settings.clip_count}
            onChange={(event) => patch({ clip_count: Number(event.target.value) })}
          />
        </label>
        <div className="grid grid-cols-2 gap-2">
          <NumberField
            label="Shortest"
            suffix="s"
            value={settings.min_len}
            disabled={disabled}
            onChange={(min_len) => patch({ min_len })}
          />
          <NumberField
            label="Longest"
            suffix="s"
            value={settings.max_len}
            disabled={disabled}
            onChange={(max_len) => patch({ max_len })}
          />
          {problem && (
            <p className="col-span-2 text-xs normal-case tracking-normal text-orange-200">{problem}</p>
          )}
        </div>
        <SelectField
          label="Whisper"
          value={settings.whisper_model}
          disabled={disabled}
          onChange={(whisper_model) =>
            patch({ whisper_model: whisper_model as Settings["whisper_model"] })
          }
          options={[
            ["tiny", "Tiny · fastest"],
            ["base", "Base · default"],
            ["small", "Small · sharper"],
            ["medium", "Medium · slow"],
          ]}
        />
        <SelectField
          label="Highlights"
          value={settings.llm_provider}
          disabled={disabled}
          onChange={(llm_provider) =>
            patch({ llm_provider: llm_provider as Settings["llm_provider"] })
          }
          options={[
            ["auto", "Auto"],
            ["heuristic", "On this machine"],
            ["gemini", "Gemini Flash"],
            ["openai", "OpenAI"],
            ["anthropic", "Anthropic"],
          ]}
        />
      </div>

      <div className="mt-4 flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <fieldset className="min-w-0">
          <legend className="text-xs uppercase tracking-[0.14em] text-mute">Captions</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {(
              [
                ["hormozi", "Hormozi"],
                ["pop", "Pop"],
                ["clean", "Clean"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                disabled={disabled}
                aria-pressed={settings.caption_style === id}
                aria-label={`${label} captions`}
                onClick={() => patch({ caption_style: id })}
                className={`rounded-2xl border px-3 py-2 text-left ${
                  settings.caption_style === id ? "border-lime bg-lime/10" : "border-line"
                }`}
              >
                <span className="block text-[10px] uppercase tracking-[0.14em] text-mute">{label}</span>
                <span
                  className={`mt-1 block text-sm ${id === "clean" ? "font-sans normal-case" : "font-display uppercase tracking-wide"}`}
                >
                  {id === "hormozi" && (
                    <>
                      STOP <span className="text-lime">SCROLLING</span>
                    </>
                  )}
                  {id === "pop" && (
                    <>
                      WAIT <span className="text-coral">FOR</span> IT
                    </>
                  )}
                  {id === "clean" && (
                    <>
                      A quieter <span className="text-lime">line</span>
                    </>
                  )}
                </span>
              </button>
            ))}
          </div>
        </fieldset>
        <div className="flex flex-wrap items-center gap-3">
          <SelectField
            label="Picture"
            value={settings.quality}
            disabled={disabled}
            onChange={(quality) => patch({ quality: quality as Settings["quality"] })}
            options={[
              ["fast", "720 × 1280"],
              ["sharp", "1080 × 1920"],
            ]}
          />
          <label className="flex items-center gap-2 text-sm text-mute">
            <input
              type="checkbox"
              className="accent-lime"
              checked={settings.use_signals}
              disabled={disabled}
              onChange={(event) => patch({ use_signals: event.target.checked })}
            />
            Audio & scene hints
          </label>
        </div>
      </div>
    </section>
  );
}

function NumberField({
  label,
  value,
  suffix,
  disabled,
  onChange,
}: {
  label: string;
  value: number;
  suffix: string;
  disabled: boolean;
  onChange: (value: number) => void;
}) {
  return (
    <label className="block text-xs uppercase tracking-[0.14em] text-mute">
      {label}
      <span className="mt-2 flex items-center rounded-xl border border-line bg-paper px-3">
        <input
          type="number"
          min={5}
          max={120}
          disabled={disabled}
          value={value}
          onChange={(event) => onChange(Number(event.target.value))}
          className="w-full bg-transparent py-2 text-sm normal-case tracking-normal text-ink outline-none"
        />
        <span className="text-mute">{suffix}</span>
      </span>
    </label>
  );
}

function SelectField({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string;
  value: string;
  options: [string, string][];
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  return (
    <label className="block text-xs uppercase tracking-[0.14em] text-mute">
      {label}
      <select
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-2 w-full rounded-xl border border-line bg-paper px-3 py-2 text-sm normal-case tracking-normal text-ink outline-none"
      >
        {options.map(([id, name]) => (
          <option key={id} value={id}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}

function ProgressPanel({ job }: { job: Job }) {
  const active = stepIndex(job.stage);
  const percent = Math.round((job.progress || 0) * 100);
  return (
    <section className="rounded-[28px] border border-line bg-panel/80 p-6 sm:p-8">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs uppercase tracking-[0.16em] text-mute">Cutting</p>
          <h2 className="mt-1 truncate font-display text-3xl italic text-ink" title={job.filename}>
            {job.filename}
          </h2>
        </div>
        <p className="font-display text-4xl italic text-lime">{percent}%</p>
      </div>
      <ol className="mt-8 grid gap-3 sm:grid-cols-4">
        {STEPS.map((step, index) => {
          const state = index < active ? "done" : index === active ? "now" : "wait";
          return (
            <li key={step.id} className="rounded-2xl border border-line px-3 py-3">
              <span
                className={`mr-2 inline-block h-2 w-2 rounded-full ${
                  state === "wait" ? "bg-line" : "bg-lime"
                }`}
              />
              <span className={state === "wait" ? "text-mute" : "text-ink"}>{step.label}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-5 text-sm text-mute">{job.detail}</p>
      <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-paper">
        <div className="h-full bg-lime transition-all" style={{ width: `${percent}%` }} />
      </div>
    </section>
  );
}

function stepIndex(stage: string): number {
  if (stage === "rendering") return 3;
  if (stage === "highlighting") return 2;
  if (stage === "transcribing") return 1;
  if (stage === "done") return 4;
  return 0;
}

function Gallery({ job, onReset }: { job: Job; onReset: () => void }) {
  const note = useMemo(() => providerNote(job.provider), [job.provider]);
  return (
    <section>
      <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display text-3xl italic text-ink">
            {job.clips.length} {job.clips.length === 1 ? "hook" : "hooks"}
          </h2>
          <p className="mt-1 flex min-w-0 text-sm text-mute">
            <span className="truncate" title={job.filename}>
              {job.filename}
            </span>
            <span className="shrink-0">&nbsp;· {note}</span>
          </p>
        </div>
        <button type="button" onClick={onReset} className="text-sm text-lime">
          Cut another
        </button>
      </div>
      {job.clips.length === 0 ? (
        <p className="rounded-2xl border border-line px-4 py-6 text-sm text-mute">
          The ranker did not keep any stretch. Widen the length range and try again.
        </p>
      ) : (
        <div className="grid grid-cols-[repeat(auto-fill,minmax(220px,280px))] gap-5">
          {job.clips.map((clip) => (
            <ClipCard key={clip.id} jobId={job.id} clip={clip} />
          ))}
        </div>
      )}
    </section>
  );
}

function ClipCard({ jobId, clip }: { jobId: string; clip: Clip }) {
  const tone = MOOD_TONE[clip.mood] ?? "bg-white/5 text-ink";
  return (
    <article className="flex flex-col rounded-[28px] border border-line bg-panel/70 p-3 shadow-phone">
      <div className="overflow-hidden rounded-[22px] bg-black">
        <video
          className="aspect-[9/16] w-full object-contain"
          controls
          playsInline
          preload="metadata"
          src={`/api/jobs/${jobId}/clips/${clip.id}/preview#t=0.5`}
        />
      </div>
      <div className="flex items-start justify-between gap-3 px-2 pt-3">
        <div>
          <p className="font-display text-4xl italic leading-none text-ink">
            {Math.round(clip.hook_score)}
          </p>
          <p className="mt-1 text-[10px] uppercase tracking-[0.16em] text-mute">Hook score</p>
        </div>
        <span className={`rounded-full px-2.5 py-1 text-xs capitalize ${tone}`}>{clip.mood}</span>
      </div>
      <h3 className="px-2 pt-3 text-lg leading-snug text-ink">{clip.title}</h3>
      <p className="px-2 pt-1 text-sm leading-relaxed text-mute">{clip.reason}</p>
      <p className="px-2 pt-2 text-xs text-mute">
        {formatSeconds(clip.start)}–{formatSeconds(clip.end)} · {clip.duration.toFixed(1)}s cut
      </p>
      <div className="mt-3 grid grid-cols-2 gap-2 px-1 pb-1">
        <a
          className="rounded-full bg-lime py-2 text-center text-sm font-medium text-paper"
          href={`/api/jobs/${jobId}/clips/${clip.id}/download`}
        >
          Download
        </a>
        <a
          className="rounded-full border border-line py-2 text-center text-sm text-ink"
          href={`/api/jobs/${jobId}/clips/${clip.id}/project`}
        >
          Editor file
        </a>
      </div>
    </article>
  );
}

function providerNote(provider: string | null): string {
  if (provider === "gemini") return "Hooks picked by Gemini";
  if (provider === "openai") return "Hooks picked by OpenAI";
  if (provider === "anthropic") return "Hooks picked by Anthropic";
  return "Hooks ranked on this machine";
}

function formatSeconds(value: number): string {
  const total = Math.max(0, Math.round(value));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}
