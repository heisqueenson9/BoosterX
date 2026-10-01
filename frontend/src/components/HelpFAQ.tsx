export function HelpFAQPage() {
  const faqs = [
    {
      q: "How does payment work with Mobile Money?",
      a: "You send the exact payment amount in GHS to our official Telecel Cash number (0202979378, Name: BOOSTX) from any network (Telecel, MTN, or AirtelTigo). After sending, upload a screenshot of your payment receipt. Our automated system verifies it instantly!"
    },
    {
      q: "Do I need an account to place an order?",
      a: "Yes. You need a free BoostX account to place orders. Sign up with your name, email and a password, and all your orders, payments and wallet balance are kept safely under your account so you can reach them from any device."
    },
    {
      q: "How long does delivery take?",
      a: "Most orders begin processing within 1 to 15 minutes of payment verification. Delivery times depend on the quantity and platform rules to ensure safe, natural growth."
    },
    {
      q: "What is your refund policy?",
      a: "If an order fails completely, 100% of your funds are refunded automatically to your BoostX wallet. If an order delivers partially, a pro-rata refund is calculated for the remaining quantity."
    },
    {
      q: "Can I request a refill if numbers drop?",
      a: "Yes! Services marked with Refill Protection qualify for automated refills within 30 days if your numbers drop below the start count."
    }
  ];

  return (
    <div className="help-page">
      <div className="page-title">
        <div>
          <h1>Help & Frequently Asked Questions</h1>
          <p>Everything you need to know about ordering, payments, and delivery on BoostX.</p>
        </div>
      </div>

      <section className="card" style={{ marginBottom: "1.5rem" }}>
        <h2>Frequently Asked Questions</h2>
        <div style={{ display: "flex", flexDirection: "column", gap: "1.25rem", marginTop: "1rem" }}>
          {faqs.map((faq, i) => (
            <div key={i} style={{ borderBottom: i < faqs.length - 1 ? "1px solid var(--border)" : "none", paddingBottom: "1rem" }}>
              <h3 style={{ fontSize: "1.1rem", marginBottom: "0.4rem" }}>{faq.q}</h3>
              <p style={{ color: "var(--muted)", lineHeight: 1.6 }}>{faq.a}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card">
        <h2>Need further assistance?</h2>
        <p style={{ color: "var(--muted)", margin: "0.5rem 0 1rem" }}>Our support team is available 24/7 to assist with payment verification or order inquiries.</p>
        <div style={{ display: "flex", gap: "1rem" }}>
          <a href="#/support" className="btn primary">Open Support Ticket</a>
        </div>
      </section>
    </div>
  );
}
