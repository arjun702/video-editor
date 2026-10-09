export type CaptionStyle = "hormozi" | "pop" | "clean";

export type Settings = {
  clip_count: number;
  min_len: number;
  max_len: number;
  caption_style: CaptionStyle;
  whisper_model: "tiny" | "base" | "small" | "medium";
  llm_provider: "auto" | "gemini" | "openai" | "anthropic" | "heuristic";
  quality: "fast" | "sharp";
  use_signals: boolean;
};

export type Clip = {
  id: string;
  title: string;
  reason: string;
  mood: string;
  hook_score: number;
  start: number;
  end: number;
  duration: number;
};

export type Job = {
  id: string;
  filename: string;
  stage: string;
  progress: number;
  detail: string;
  error: string | null;
  provider: string | null;
  clips: Clip[];
  settings: Settings;
};

export const defaultSettings: Settings = {
  clip_count: 4,
  min_len: 15,
  max_len: 45,
  caption_style: "hormozi",
  whisper_model: "base",
  llm_provider: "auto",
  quality: "fast",
  use_signals: true,
};

function appendSettings(body: FormData, settings: Settings) {
  body.append("clip_count", String(settings.clip_count));
  body.append("min_len", String(settings.min_len));
  body.append("max_len", String(settings.max_len));
  body.append("caption_style", settings.caption_style);
  body.append("whisper_model", settings.whisper_model);
  body.append("llm_provider", settings.llm_provider);
  body.append("quality", settings.quality);
  body.append("use_signals", settings.use_signals ? "true" : "false");
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
  } catch {
    /* ignore */
  }
  return "The request failed.";
}

export async function fetchJob(id: string): Promise<Job> {
  const response = await fetch(`/api/jobs/${id}`);
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json();
}

export function postForm(
  url: string,
  body: FormData,
  onProgress?: (fraction: number) => void,
): Promise<Job> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("POST", url);
    request.responseType = "json";
    request.upload.onprogress = (event) => {
      if (onProgress && event.lengthComputable) {
        onProgress(event.loaded / event.total);
      }
    };
    request.onerror = () => reject(new Error("Could not reach the local Spool server."));
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        resolve(request.response as Job);
        return;
      }
      const detail = request.response?.detail;
      reject(new Error(typeof detail === "string" ? detail : "The request failed."));
    };
    request.send(body);
  });
}

export function uploadVideo(
  file: File,
  settings: Settings,
  onProgress: (fraction: number) => void,
): Promise<Job> {
  const body = new FormData();
  body.append("file", file);
  appendSettings(body, settings);
  return postForm("/api/jobs", body, onProgress);
}

export function startSample(settings: Settings): Promise<Job> {
  const body = new FormData();
  // The sample reel is ~28s. Keep a tight window so the demo lands on a real hook.
  appendSettings(body, {
    ...settings,
    clip_count: Math.min(settings.clip_count, 2),
    min_len: 8,
    max_len: 16,
    quality: "fast",
    llm_provider: settings.llm_provider === "auto" ? "heuristic" : settings.llm_provider,
    use_signals: false,
  });
  return postForm("/api/sample", body);
}
