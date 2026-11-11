// Gus captions relay (Cloudflare Worker)
//
// HeyGen  --"video finished"-->  this Worker  --starts-->  GitHub caption job
//
// Settings needed in Cloudflare (Settings -> Variables and Secrets):
//   GITHUB_REPO     (text)    e.g. yourname/gus-captions
//   GITHUB_TOKEN    (secret)  GitHub fine-grained token with Contents: Read and write on that repo
//   HEYGEN_API_KEY  (secret)  your HeyGen API key (only used once, by /setup)
//   RELAY_TOKEN     (secret)  any long random password you make up
//
// One-time: open  https://<your-worker>.workers.dev/setup?token=<RELAY_TOKEN>  in a browser
// to register this Worker with HeyGen.

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const token = url.searchParams.get("token") || "";
    const authorized = env.RELAY_TOKEN && token === env.RELAY_TOKEN;

    // ---- one-time: register the webhook with HeyGen
    if (url.pathname === "/setup") {
      if (!authorized) return text("Wrong or missing token.", 401);
      const hookUrl = `${url.origin}/heygen?token=${encodeURIComponent(env.RELAY_TOKEN)}`;
      const headers = { "X-Api-Key": env.HEYGEN_API_KEY, "Content-Type": "application/json", Accept: "application/json" };

      // skip if already registered
      try {
        const list = await fetch("https://api.heygen.com/v1/webhook/endpoint.list", { headers });
        const lj = await list.json();
        const existing = (lj.data || []).find((e) => e.url === hookUrl);
        if (existing) return text("Already connected to HeyGen. You're all set.");
      } catch (e) { /* fall through and try to add */ }

      const r = await fetch("https://api.heygen.com/v1/webhook/endpoint.add", {
        method: "POST",
        headers,
        body: JSON.stringify({ url: hookUrl, events: ["avatar_video.success"] }),
      });
      const body = await r.text();
      if (!r.ok) return text(`HeyGen said no (${r.status}): ${body}`, 502);
      return text("Webhook registered with HeyGen. You're all set.\n\n" + body);
    }

    // ---- HeyGen calls this when a video finishes
    if (url.pathname === "/heygen") {
      if (request.method !== "POST") return text("ok"); // HeyGen may check the URL first
      if (!authorized) return text("Wrong or missing token.", 401);
      let payload = {};
      try { payload = await request.json(); } catch (e) { return text("bad json", 400); }
      if (payload.event_type !== "avatar_video.success") return text("ignored: " + payload.event_type);
      const videoId = payload.event_data && payload.event_data.video_id;
      if (!videoId) return text("no video_id", 400);

      const gh = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/dispatches`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${env.GITHUB_TOKEN}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
          "User-Agent": "gus-captions-relay",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ event_type: "heygen_video", client_payload: { video_id: videoId } }),
      });
      if (gh.status === 204) return text("caption job started for " + videoId);
      return text(`GitHub said no (${gh.status}): ${await gh.text()}`, 502);
    }

    return text("Gus captions relay is running.");
  },
};

function text(s, status = 200) {
  return new Response(s, { status, headers: { "Content-Type": "text/plain; charset=utf-8" } });
}
