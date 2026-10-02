// Scroll-linked enhancement: native scrolling, no background animation loop.
// The complete page remains readable if JavaScript or motion is disabled.
const root = document.querySelector('.living-pulse');
const preference = matchMedia('(prefers-reduced-motion: reduce)');
const clamp = value => Math.min(1, Math.max(0, value));

if (root) {
  const hero = document.querySelector('.lp-hero-wrap');
  const ring = document.querySelector('.lp-art');
  const contact = document.querySelector('.lp-contact-wrap');
  const field = document.querySelector('.lp-footer-particles');
  const blocks = [...document.querySelectorAll('.lp-catalog h2, .lp-method h2, .lp-steps li, .lp-contact-intro')]
    .map(element => ({element, shift: 0}));
  let frame = 0;
  let enabled = false;

  function render() {
    frame = 0;
    if (!enabled || document.hidden) return;
    const height = innerHeight;
    const compact = innerWidth <= 820;
    // Read all geometry before applying styles. Subtract our own translation
    // so repeated renders at the same scroll position cannot drift.
    const heroBox = hero.getBoundingClientRect();
    const contactBox = contact.getBoundingClientRect();
    const progress = clamp(-heroBox.top / Math.max(1, heroBox.height));
    const fieldProgress = clamp((height - contactBox.top) / (height + contactBox.height));
    const reveals = blocks.map(block => {
      const top = block.element.getBoundingClientRect().top - block.shift;
      return clamp((height * .96 - top) / Math.max(1, height * .32));
    });

    ring.style.setProperty('--lp-ring-y', `${progress * (compact ? 36 : 105)}px`);
    ring.style.setProperty('--lp-ring-x', `${progress * (compact ? -6 : -30)}px`);
    ring.style.setProperty('--lp-ring-turn', `${progress * (compact ? 38 : 72)}deg`);
    ring.style.setProperty('--lp-ring-scale', String(1 - progress * .07));
    field.style.setProperty('--lp-field-x', `${(fieldProgress - .5) * (compact ? 30 : 90)}px`);
    field.style.setProperty('--lp-field-y', `${(.5 - fieldProgress) * 48}px`);
    blocks.forEach((block, index) => {
      const reveal = reveals[index];
      block.shift = (1 - reveal) * (compact ? 18 : 32);
      block.element.style.setProperty('--lp-reveal-y', `${block.shift}px`);
      block.element.style.setProperty('--lp-reveal-opacity', String(.32 + reveal * .68));
    });
  }

  function schedule() {
    if (enabled && !document.hidden && !frame) frame = requestAnimationFrame(render);
  }

  function configure() {
    enabled = !preference.matches;
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    blocks.forEach(block => {
      block.shift = 0;
      block.element.classList.toggle('lp-motion-block', enabled);
      block.element.style.removeProperty('--lp-reveal-y');
      block.element.style.removeProperty('--lp-reveal-opacity');
    });
    root.dataset.motion = enabled ? 'scroll' : 'reduced';
    schedule();
  }

  addEventListener('scroll', schedule, {passive: true});
  addEventListener('resize', schedule, {passive: true});
  addEventListener('pageshow', schedule);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
    else schedule();
  });
  preference.addEventListener('change', configure);
  // Account for a loaded catalogue, expanded service, mobile menu and fonts.
  if ('ResizeObserver' in window) {
    const observer = new ResizeObserver(schedule);
    observer.observe(document.querySelector('main'));
    observer.observe(document.querySelector('.lp-header'));
  }
  document.addEventListener('toggle', schedule, true);
  document.fonts.ready.then(schedule);
  configure();
}
