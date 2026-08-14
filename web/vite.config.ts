import { defineConfig } from 'vite';

// Relative asset URLs make dist/ deployable at a domain root or any subpath.
export default defineConfig({ base: './' });
