import { AudienceSection } from "@/components/marketing/AudienceSection";
import { CtaSection } from "@/components/marketing/CtaSection";
import { ExamplesSection } from "@/components/marketing/ExamplesSection";
import { FaqSection } from "@/components/marketing/FaqSection";
import { Hero } from "@/components/marketing/Hero";
import { HowItWorksSection } from "@/components/marketing/HowItWorksSection";
import { MarketingFooter } from "@/components/marketing/MarketingFooter";
import { MarketingHeader } from "@/components/marketing/MarketingHeader";
import { PricingSection } from "@/components/marketing/PricingSection";
import { RevealOnScroll } from "@/components/marketing/RevealOnScroll";
import { SessionRedirect } from "@/components/marketing/SessionRedirect";
import { ShiftSection } from "@/components/marketing/ShiftSection";
import { TrustSection } from "@/components/marketing/TrustSection";
import { VideoSection } from "@/components/marketing/VideoSection";

export default function HomePage() {
  return (
    <>
      <SessionRedirect />
      <MarketingHeader />
      <main className="relative" style={{ zIndex: 2 }}>
        <Hero />
        <VideoSection />
        <ShiftSection />
        <ExamplesSection />
        <HowItWorksSection />
        <TrustSection />
        <AudienceSection />
        <PricingSection />
        <FaqSection />
        <CtaSection />
        <MarketingFooter />
      </main>
      <RevealOnScroll />
    </>
  );
}
