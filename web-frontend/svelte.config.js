import adapter from "@sveltejs/adapter-static";

/** @type {import('@sveltejs/kit').Config} */
const config = {
  kit: {
    adapter: adapter({
      pages: "../cli/src/pkm/web/static",
      assets: "../cli/src/pkm/web/static",
      fallback: "index.html",
      precompress: false,
      strict: false,
    }),
    alias: {
      $lib: "./src/lib",
    },
  },
};

export default config;
