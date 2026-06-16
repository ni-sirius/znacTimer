def export_pdf(stats, output_path):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    pdf = canvas.Canvas(output_path, pagesize=A4)
    pdf.drawString(50, 800, "Monthly Time Report")
    pdf.drawString(50, 770, f"Year: {stats.year}")
    pdf.drawString(50, 750, f"Month: {stats.month}")
    pdf.drawString(50, 730, f"Overtime: {stats.overtime:.2f} h")
    pdf.save()
