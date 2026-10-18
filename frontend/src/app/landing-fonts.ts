// Shared brand typefaces, self-hosted from node_modules (OFL-1.1 @fontsource-variable packages) so the production build
// needs no network. Each export keeps the `.variable` shape `next/font` had: a class that defines the CSS variable the
// stylesheet reads. The class rules live in globals.css (.kairos-font-*).
import "@fontsource-variable/dm-sans";
import "@fontsource-variable/instrument-sans";

export const instrumentSans = { variable: "kairos-font-instrument" };
export const dmSans = { variable: "kairos-font-dm" };
