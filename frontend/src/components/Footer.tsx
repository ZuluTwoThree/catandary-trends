export default function Footer() {
  return (
    <footer className="border-t border-border mt-24">
      <div className="mx-auto max-w-7xl px-6 md:px-12 py-6 flex flex-col md:flex-row items-center justify-between gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          &copy; {new Date().getFullYear()} Catandary
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          Powered by{" "}
          <a
            href="https://catandary.de"
            className="text-accent hover:underline"
          >
            Catandary Foresight
          </a>
        </span>
      </div>
    </footer>
  );
}
