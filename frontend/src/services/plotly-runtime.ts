import { Buffer } from "buffer";
import Plotly from "plotly.js/lib/core";
import ScatterGL from "plotly.js/lib/scattergl";

const runtimeGlobal = globalThis as typeof globalThis & { Buffer?: typeof Buffer };
runtimeGlobal.Buffer ||= Buffer;

// Register only the WebGL 2D trace used by the research platform. Keeping the
// registry local avoids shipping maps, 3D, finance and statistical trace types.
Plotly.register([ScatterGL]);

export default Plotly;
