import {
  AbsoluteFill,
  Audio,
  Composition,
  interpolate,
  Sequence,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import content from "./scenes.json";
import timings from "../public/voiceover/timings.json";

const fps = 30;
const overlap = 18;
const timingById: Record<string, { audioFrames: number; durationInFrames: number }> = timings;
const scenes = content.map((scene) => ({ ...scene, ...timingById[scene.id] }));
const durationInFrames = scenes.reduce((total, scene) => total + scene.durationInFrames, 0) - overlap * (scenes.length - 1);

const colors = {
  ink: "#251831",
  soft: "#695a72",
  purple: "#7446ba",
  purpleDark: "#4d2b7f",
  lavender: "#eee5f8",
  paper: "#fcfaf6",
  line: "#dfd8df",
  green: "#438b69",
};

const card: React.CSSProperties = {
  position: "absolute",
  border: `1px solid ${colors.line}`,
  borderRadius: 22,
  background: colors.paper,
  boxShadow: "0 28px 80px #2e1d3d1a",
};

const label: React.CSSProperties = {
  color: colors.soft,
  fontFamily: "Arial, sans-serif",
  fontSize: 16,
  fontWeight: 700,
  letterSpacing: 3,
};

const chip: React.CSSProperties = {
  display: "inline-flex",
  alignItems: "center",
  gap: 12,
  border: `1px solid ${colors.line}`,
  borderRadius: 999,
  padding: "12px 18px",
  color: colors.soft,
  background: colors.paper,
  fontFamily: "Arial, sans-serif",
  fontSize: 16,
};

const renderers: Record<string, React.FC<{ frame: number }>> = {
  intro: IntroVisual,
  sources: SourcesVisual,
  voice: VoiceVisual,
  evidence: EvidenceVisual,
  boundary: BoundaryVisual,
  "use-cases": UseCasesVisual,
  publish: PublishVisual,
};

const StoryScene: React.FC<{
  scene: (typeof scenes)[number];
}> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps: videoFps } = useVideoConfig();
  const enter = spring({ frame, fps: videoFps, config: { damping: 22, stiffness: 90, mass: 0.8 } });
  const fade = interpolate(frame, [0, 14, scene.durationInFrames - 12, scene.durationInFrames], [0, 1, 1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const Visual = renderers[scene.visual];

  return (
    <AbsoluteFill style={{
      opacity: fade,
      transform: `translateY(${interpolate(enter, [0, 1], [34, 0])}px)`,
      backgroundColor: "#f8f6ef",
      backgroundImage: "radial-gradient(#7446ba16 1px, transparent 1px), radial-gradient(ellipse at 80% 35%, #eee5f8 0%, transparent 36%)",
      backgroundSize: "28px 28px, 100% 100%",
      color: colors.ink,
      fontFamily: "Arial, sans-serif",
    }}>
      <div style={{ position: "absolute", top: 90, left: 132, ...label, color: colors.purpleDark }}>{scene.eyebrow}</div>
      <div style={{ position: "absolute", left: 132, top: 300, width: 770 }}>
        <h1 style={{ margin: 0, fontFamily: "Georgia, serif", fontWeight: 400, fontSize: 92, lineHeight: 1.04, letterSpacing: -3.5, whiteSpace: "pre-line" }}>{scene.title}</h1>
        <p style={{ margin: "30px 0 0", maxWidth: 670, color: colors.soft, fontSize: 28, lineHeight: 1.5 }}>{scene.note}</p>
        <div style={{ marginTop: 45, ...chip }}><span style={{ width: 9, height: 9, borderRadius: 50, background: colors.green }} />Grounded in your approved material</div>
      </div>
      <div style={{ position: "absolute", top: 195, right: 108, width: 820, height: 650 }}>
        <Visual frame={frame} />
      </div>
      <div style={{ position: "absolute", left: 132, right: 132, bottom: 56, padding: "20px 28px", borderRadius: 14, color: "#fff", background: "#251831ee", boxShadow: "0 14px 40px #25183120", textAlign: "center", fontSize: 27, lineHeight: 1.38, whiteSpace: "pre-line" }}>{scene.subtitle}</div>
      <Audio src={staticFile(`voiceover/${scene.id}.wav`)} volume={0.96} />
    </AbsoluteFill>
  );
};

const Film: React.FC = () => {
  let from = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: "#f8f6ef" }}>
      {scenes.map((scene) => {
        const start = from;
        from += scene.durationInFrames - overlap;
        return (
          <Sequence key={scene.id} from={start} durationInFrames={scene.durationInFrames}>
            <StoryScene scene={scene} />
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

export const MyComposition: React.FC = () => (
  <Composition
    id="PitchroomExplainer"
    component={Film}
    durationInFrames={durationInFrames}
    fps={fps}
    width={1920}
    height={1080}
  />
);

function IntroVisual({ frame }: { frame: number }) {
  const pulse = 1 + Math.sin(frame / 15) * 0.035;
  const documents = [
    { name: "Project update", tag: "PPTX", x: 70, y: 110, rotate: -8 },
    { name: "Team handbook", tag: "PDF", x: 385, y: 355, rotate: 5 },
    { name: "Website pages", tag: "WEB", x: 515, y: 95, rotate: 8 },
  ];
  return <>
    <div style={{ position: "absolute", inset: 76, border: "1px solid #7446ba2b", borderRadius: "50%", transform: "rotate(-13deg)" }} />
    {documents.map((document, index) => <div key={document.name} style={{ ...card, left: document.x, top: document.y + Math.sin(frame / 18 + index) * 8, width: 270, padding: 24, transform: `rotate(${document.rotate}deg)` }}><div style={label}>{document.tag}</div><div style={{ marginTop: 20, fontSize: 22, fontWeight: 600 }}>{document.name}</div><div style={{ display: "flex", gap: 7, marginTop: 18 }}>{[1, 0.75, 0.58].map((width, i) => <i key={i} style={{ height: 5, width: `${width * 100}%`, borderRadius: 4, background: "#e5dfe8" }} />)}</div></div>)}
    <div style={{ ...card, left: 242, top: 240, display: "grid", placeItems: "center", width: 230, height: 230, borderRadius: "50%", borderColor: "#9c7dc0", background: "#fcfaf6", transform: `scale(${pulse})` }}>
      <div style={{ width: 126, height: 126, display: "grid", placeItems: "center", borderRadius: "50%", color: "white", background: colors.purpleDark, boxShadow: "0 0 0 18px #7446ba18" }}><WaveMark /></div>
      <div style={{ position: "absolute", bottom: 21, ...label, fontSize: 11 }}>PITCHROOM AI</div>
    </div>
  </>;
}

function SourcesVisual({ frame }: { frame: number }) {
  const slide = (offset: number) => interpolate(frame, [0, 24], [90 + offset, offset], { extrapolateRight: "clamp" });
  return <>
    <div style={{ ...card, left: 8, top: 70, width: 760, height: 475, padding: 31 }}>
      <div style={label}>YOUR SOURCES · PRIVATE</div>
      <div style={{ display: "flex", gap: 14, marginTop: 27, alignItems: "center" }}><span style={{ color: colors.purpleDark, fontSize: 25 }}>↗</span><span style={{ color: colors.ink, fontSize: 24 }}>northstar.studio/services</span><span style={{ marginLeft: "auto", ...chip, padding: "8px 14px", color: colors.green, borderColor: "#cce1d4", fontSize: 14 }}>Imported</span></div>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 15, marginTop: 24 }}>
        {[["PDF", "Service overview"], ["PPTX", "Project proposal"], ["DOCX", "Team playbook"], ["WEB", "About & FAQs"]].map(([tag, title], i) => <div key={tag} style={{ display: "flex", alignItems: "center", gap: 17, padding: 20, border: `1px solid ${colors.line}`, borderRadius: 15, transform: `translateY(${slide(i * 8)}px)`, opacity: interpolate(frame, [0, 24], [0, 1], { extrapolateRight: "clamp" }) }}><span style={{ display: "grid", placeItems: "center", width: 49, height: 49, borderRadius: 12, color: colors.purpleDark, background: colors.lavender, fontSize: 12, fontWeight: 700 }}>{tag}</span><span style={{ fontSize: 18, fontWeight: 600 }}>{title}</span><span style={{ marginLeft: "auto", color: colors.green, fontSize: 20 }}>✓</span></div>)}
      </div>
    </div>
    <div style={{ position: "absolute", right: -4, bottom: 6, ...chip, color: colors.purpleDark, boxShadow: "0 15px 45px #2e1d3d22" }}>Review everything before it can answer</div>
  </>;
}

function VoiceVisual({ frame }: { frame: number }) {
  const heights = [20, 32, 54, 72, 44, 88, 112, 63, 39, 78, 104, 49, 30, 66, 92, 44, 25, 60, 86, 37, 24, 48, 71, 34, 20];
  return <>
    <div style={{ position: "absolute", inset: 42, border: "1px solid #7446ba24", borderRadius: "50%", transform: "rotate(-16deg)" }} />
    <div style={{ ...card, left: 55, top: 125, width: 700, padding: 32 }}>
      <div style={label}>YOU · VOICE</div>
      <div style={{ marginTop: 20, fontFamily: "Georgia, serif", fontSize: 34 }}>What is blocking the launch?</div>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, height: 145, marginTop: 14 }}>
        {heights.map((height, index) => <i key={index} style={{ width: 7, height: height * (0.35 + Math.abs(Math.sin(frame / 8 + index * 0.8)) * 0.65), borderRadius: 99, background: index < 18 ? colors.purple : "#d6cae2" }} />)}
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 16, paddingTop: 21, borderTop: `1px solid ${colors.line}` }}><div style={{ display: "grid", placeItems: "center", width: 48, height: 48, borderRadius: 50, background: colors.purpleDark, color: "white" }}><WaveMark /></div><div><div style={{ fontWeight: 700 }}>Pitchroom is listening</div><div style={{ marginTop: 5, color: colors.soft, fontSize: 15 }}>Voice or text · Your choice</div></div><span style={{ marginLeft: "auto", ...chip, color: colors.green }}>Ready for a follow-up</span></div>
    </div>
  </>;
}

function EvidenceVisual({ frame }: { frame: number }) {
  const lift = interpolate(frame, [0, 30], [42, 0], { extrapolateRight: "clamp" });
  return <div style={{ ...card, left: 20, top: 63, width: 750, padding: 33, transform: `translateY(${lift}px)` }}>
    <div style={{ display: "flex", justifyContent: "space-between", ...label }}><span>GROUNDED ANSWER</span><span style={{ color: colors.green }}>● SOURCE FOUND</span></div>
    <div style={{ marginTop: 28, fontFamily: "Georgia, serif", fontSize: 34, lineHeight: 1.35 }}>The CSV date bug is the main blocker. Mei owns the fix, and a retest is due 18 July.</div>
    <div style={{ marginTop: 27, padding: 23, border: "1px solid #d8c9e5", borderRadius: 15, background: "#f7f2fb" }}><div style={label}>MATCHING EXCERPT</div><div style={{ marginTop: 13, color: colors.soft, fontSize: 18, lineHeight: 1.5 }}>“Mei will resolve the CSV date mismatch. Export retesting is scheduled for 18 July.”</div></div>
    <div style={{ display: "flex", alignItems: "center", gap: 11, marginTop: 18, ...chip, color: colors.purpleDark, background: colors.lavender, border: "none" }}><span>↗</span> Slide 04 · Weekly project update</div>
  </div>;
}

function BoundaryVisual({ frame }: { frame: number }) {
  const ring = 1 + Math.sin(frame / 16) * 0.025;
  return <>
    <div style={{ ...card, left: 24, top: 74, width: 740, padding: 30 }}>
      <div style={label}>YOU · FOLLOW-UP</div><div style={{ marginTop: 16, fontFamily: "Georgia, serif", fontSize: 31 }}>And what is the refund policy?</div>
      <div style={{ display: "flex", gap: 15, marginTop: 28, padding: 24, borderRadius: 16, background: "#f3edf8", transform: `scale(${ring})`, transformOrigin: "left center" }}><div style={{ display: "grid", placeItems: "center", flex: "0 0 48px", height: 48, borderRadius: 50, background: colors.purpleDark, color: "white" }}><WaveMark /></div><div><div style={label}>PITCHROOM · APPROVED SOURCES ONLY</div><div style={{ marginTop: 14, fontSize: 23, lineHeight: 1.45 }}>I couldn't find that in these sources.</div></div></div>
      <div style={{ display: "flex", gap: 15, marginTop: 25, color: colors.soft, fontSize: 17 }}><span style={{ color: colors.green }}>✓</span><span>No made-up policy.<br /><b style={{ color: colors.ink }}>Clear about what the material doesn't say.</b></span></div>
    </div>
  </>;
}

function UseCasesVisual({ frame }: { frame: number }) {
  const cases = [["01", "TEAM HANDBOOK", "Find everyday answers", "#f3edf8"], ["02", "COURSE NOTES", "Revisit a lesson", "#edf2f6"], ["03", "SERVICE GUIDE", "Explain what’s included", "#f4f0e5"], ["04", "PROJECT DECK", "Find decisions & owners", "#eaf2ed"]];
  return <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 18, paddingTop: 26 }}>
    {cases.map(([number, title, note, background], index) => <div key={number} style={{ ...card, position: "relative", minHeight: 223, padding: 25, background, transform: `translateY(${interpolate(frame, [0, 28], [74 + (index % 2) * 25, 0], { extrapolateRight: "clamp" })}px)`, opacity: interpolate(frame, [0, 28], [0, 1], { extrapolateRight: "clamp" }) }}><div style={{ ...label, color: colors.purpleDark }}>{number} / {title}</div><div style={{ marginTop: 32, fontFamily: "Georgia, serif", fontSize: 27 }}>{note}</div><div style={{ position: "absolute", right: 24, bottom: 24, color: colors.purple, fontSize: 30 }}>↗</div></div>)}
  </div>;
}

function PublishVisual({ frame }: { frame: number }) {
  const progress = interpolate(frame, [18, 44], [0, 1], { extrapolateLeft: "clamp", extrapolateRight: "clamp" });
  return <>
    <div style={{ ...card, left: 25, top: 94, width: 730, padding: 34 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><div><div style={label}>YOUR ASSISTANT</div><div style={{ marginTop: 12, fontFamily: "Georgia, serif", fontSize: 30 }}>Northstar service guide</div></div><div style={{ ...chip, color: colors.green, borderColor: "#cce1d4" }}>● Private</div></div>
      <div style={{ height: 1, margin: "26px 0", background: colors.line }} />
      <div style={{ display: "flex", alignItems: "center", gap: 18 }}><span style={{ display: "grid", placeItems: "center", width: 48, height: 48, borderRadius: 50, background: colors.lavender, color: colors.purpleDark, fontSize: 25 }}>↗</span><div><div style={{ fontWeight: 700, fontSize: 18 }}>Approved source snapshot</div><div style={{ marginTop: 5, color: colors.soft, fontSize: 15 }}>Website + 3 reviewed guides</div></div><div style={{ width: 60, height: 32, marginLeft: "auto", padding: 4, borderRadius: 99, background: colors.purple, transform: `translateX(${progress * 2}px)` }}><div style={{ width: 24, height: 24, borderRadius: 50, background: "white", transform: `translateX(${progress * 28}px)` }} /></div></div>
      <div style={{ marginTop: 27, padding: "17px 20px", border: `1px solid ${colors.line}`, borderRadius: 13, color: colors.soft, fontSize: 17 }}>pitchroom.ai/a/northstar-service-guide <span style={{ float: "right", color: colors.purpleDark }}>Copy link</span></div>
      <div style={{ display: "flex", alignItems: "center", gap: 9, marginTop: 18, color: colors.soft, fontSize: 14 }}>You can revoke this visitor link at any time.</div>
    </div>
  </>;
}

function WaveMark() {
  return <svg width="36" height="36" viewBox="0 0 36 36" fill="none" aria-hidden="true"><path d="M7 19v-2m5 7V12m5 12V8m5 16V12m5 7v-2" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" /></svg>;
}
