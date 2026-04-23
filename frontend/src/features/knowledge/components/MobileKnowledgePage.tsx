import { Link } from 'react-router-dom';
import { Lock, ArrowLeft } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { GlobalBioTab } from './GlobalBioTab';
import { ProjectsTab } from './ProjectsTab';
import { ExtractionJobsTab } from './ExtractionJobsTab';
import { PrivacyTab } from './PrivacyTab';

// K19f.1 — single-column mobile shell. Replaces the 7-tab desktop
// navigation at viewports <768px. Only the three "primary" sections
// (Global bio, Projects, Extraction jobs) surface here; Entities,
// Timeline, and Raw drawers are hidden behind a "use desktop" notice
// because their grids + slide-overs need horizontal room that a
// phone doesn't offer. Privacy stays reachable via a footer link —
// the desktop route keeps serving it (the PrivacyTab layout is
// already vertical-friendly).
//
// Sections reuse the existing desktop tab components inline — MVP
// approach. If the embedded components turn out cramped in practice,
// K19f Cycle β will build simplified variants (K19f.2/.3/.4 in the
// plan). See D-K19d-β-01 + D-K19e-β-02 for grids that will grow
// responsive card layouts when those hidden tabs get mobile variants
// in a future cycle.

interface SectionProps {
  heading: string;
  children: React.ReactNode;
  testId: string;
}

function Section({ heading, children, testId }: SectionProps) {
  return (
    <section className="mb-8" data-testid={testId}>
      <h2 className="mb-3 font-serif text-base font-semibold">{heading}</h2>
      {children}
    </section>
  );
}

export function MobileKnowledgePage() {
  const { t } = useTranslation('knowledge');

  return (
    <div
      className="mx-auto max-w-[640px] px-4 py-4"
      data-testid="mobile-knowledge-page"
    >
      <h1 className="mb-1 font-serif text-xl font-semibold">
        {t('page.title')}
      </h1>
      <p className="mb-5 text-[13px] text-muted-foreground">
        {t('page.subtitle')}
      </p>

      <Section
        heading={t('mobile.sections.global')}
        testId="mobile-section-global"
      >
        <GlobalBioTab />
      </Section>

      <Section
        heading={t('mobile.sections.projects')}
        testId="mobile-section-projects"
      >
        <ProjectsTab />
      </Section>

      <Section
        heading={t('mobile.sections.jobs')}
        testId="mobile-section-jobs"
      >
        <ExtractionJobsTab />
      </Section>

      <aside
        className="mt-6 rounded-lg border border-dashed bg-muted/30 px-4 py-3 text-[12px]"
        data-testid="mobile-desktop-only-banner"
      >
        <p className="mb-1 font-medium">{t('mobile.desktopOnly.title')}</p>
        <p className="text-muted-foreground">
          {t('mobile.desktopOnly.body')}
        </p>
      </aside>

      <Link
        to="/knowledge/privacy"
        className="mt-4 inline-flex items-center gap-1.5 text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        data-testid="mobile-privacy-link"
      >
        <Lock className="h-3.5 w-3.5" />
        {t('mobile.privacyLink')}
      </Link>
    </div>
  );
}

// K19f.1 — mobile shell for the Privacy route. Users arrive here via
// MobileKnowledgePage's privacyLink, then need a back affordance to
// return to the knowledge sections. Renders only the PrivacyTab body
// (skipping the 7-tab desktop nav which overflows a phone viewport)
// plus a back link. Fixed in post-/review-impl M1 after the initial
// cycle let mobile+privacy fall through to the broken desktop layout.
export function MobilePrivacyShell() {
  const { t } = useTranslation('knowledge');
  return (
    <div
      className="mx-auto max-w-[640px] px-4 py-4"
      data-testid="mobile-privacy-shell"
    >
      <Link
        to="/knowledge/projects"
        className="mb-4 inline-flex items-center gap-1.5 text-[12px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
        data-testid="mobile-privacy-back"
      >
        <ArrowLeft className="h-3.5 w-3.5" />
        {t('mobile.backToKnowledge')}
      </Link>
      <h1 className="mb-5 font-serif text-xl font-semibold">
        {t('page.tabs.privacy')}
      </h1>
      <PrivacyTab />
    </div>
  );
}
