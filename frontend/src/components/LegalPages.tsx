export function LegalPage({ type }: { type: string }) {
  const content: Record<string, { title: string; subtitle: string; text: string[] }> = {
    terms: {
      title: "Terms of Service",
      subtitle: "Last updated: September 2026",
      text: [
        "1. Acceptance of Terms: By using BoostX, you agree to comply with all applicable terms and conditions governed by the laws of Ghana.",
        "2. Service Availability: BoostX provides social media promotional and marketing services. We do not guarantee specific audience engagement or permanent retainment.",
        "3. Account Responsibility: Users are responsible for maintaining the privacy of their session cookies and credentials.",
        "4. Payment Terms: All payments are processed in Ghana Cedi (GHS) via Mobile Money. Network transfer fees must be borne by the sender."
      ]
    },
    privacy: {
      title: "Privacy Policy",
      subtitle: "Last updated: September 2026",
      text: [
        "1. Data Collection: BoostX collects minimal information needed to process orders: payment receipts, target URLs, and your account and session identifier cookies.",
        "2. Cookie Usage: HttpOnly cookies are used to keep you securely signed in to your account.",
        "3. Third Party Sharing: BoostX does not sell or share customer personal information with external advertising networks.",
        "4. Security: Payment screenshots and transaction data are processed securely using encrypted transport and vision AI engines."
      ]
    },
    refunds: {
      title: "Refund Policy",
      subtitle: "Last updated: September 2026",
      text: [
        "1. Failed Orders: If an order fails before start, 100% of the charged GHS amount is refunded automatically to your wallet balance.",
        "2. Partial Orders: If a provider delivers part of an order and cancels the remainder, a pro-rata refund is calculated for the undelivered items.",
        "3. Completed Orders: Once an order is fully completed by the provider, it cannot be refunded unless eligible under refill protection.",
        "4. Cash Out: Wallet balances may be refunded back to your original Mobile Money number upon admin review."
      ]
    },
    cookies: {
      title: "Cookie Policy",
      subtitle: "Last updated: September 2026",
      text: [
        "1. Essential Cookies: We use essential HttpOnly cookies to keep you signed in to your account.",
        "2. CSRF Security: Secure anti-CSRF token cookies are used to prevent cross-site request forgery attacks.",
        "3. Managing Cookies: You can clear cookies through your browser settings, though you will be signed out and need to log in again."
      ]
    },
    security: {
      title: "Security Policy",
      subtitle: "Last updated: September 2026",
      text: [
        "1. Infrastructure: BoostX runs on isolated Flask backend application servers with double-spend protection.",
        "2. CSRF & Auth Protection: All mutating endpoints enforce strict CSRF token headers and session version checks.",
        "3. Vision AI Verification: Payment receipts are validated automatically using machine vision algorithms."
      ]
    },
    disclaimer: {
      title: "Disclaimer",
      subtitle: "Last updated: September 2026",
      text: [
        "1. Independent Service: BoostX is an independent service provider and is not affiliated with TikTok, Instagram, Facebook, X, or Telegram.",
        "2. Account Compliance: Users should ensure their social media accounts comply with third-party platform terms.",
        "3. Service Guarantee: Results are subject to platform algorithms and public account visibility."
      ]
    }
  };

  const page = content[type] || content.terms;

  return (
    <div className="legal-page">
      <div className="page-title">
        <div>
          <h1>{page.title}</h1>
          <p>{page.subtitle}</p>
        </div>
      </div>
      <section className="card">
        <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
          {page.text.map((p, i) => (
            <p key={i} style={{ lineHeight: 1.7, color: "var(--muted)" }}>{p}</p>
          ))}
        </div>
      </section>
    </div>
  );
}
