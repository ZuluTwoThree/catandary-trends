export default function TrendsEmpty({ vertical }: { vertical: string | null }) {
  return (
    <div className="text-center py-20">
      <p className="text-muted text-lg">
        No trends yet
        {vertical ? ` in ${vertical}` : ""}
      </p>
      <p className="text-muted text-sm mt-2">
        The pipeline is running — new signals will appear here once classified.
      </p>
    </div>
  );
}
