// Decorative animated backdrop: soft palette circles drifting upward. Pure CSS
// animation (see .bubble in index.css); rendered once, behind all content.
const COLORS = [
  "#A5AF79",
  "#E8A07C",
  "#9CB080",
  "#618764",
  "#2B5748",
  "#827148",
];

// size (px), left (%), duration (s), delay (s)
const BUBBLES = [
  [220, 6, 19, 0],
  [120, 22, 14, 3],
  [300, 40, 25, 6],
  [90, 58, 13, 2],
  [180, 72, 21, 8],
  [140, 86, 16, 5],
  [70, 14, 11, 7],
  [240, 50, 28, 11],
  [110, 92, 17, 1],
];

export default function Background() {
  return (
    <div className="bg-anim" aria-hidden="true">
      {BUBBLES.map(([size, left, dur, delay], i) => (
        <span
          key={i}
          className="bubble"
          style={{
            width: size,
            height: size,
            left: `${left}%`,
            background: COLORS[i % COLORS.length],
            animationDuration: `${dur}s`,
            animationDelay: `${delay}s`,
          }}
        />
      ))}
    </div>
  );
}
