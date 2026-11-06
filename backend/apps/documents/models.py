from django.conf import settings
from django.db import models

from apps.workspaces.models import Workspace


class Document(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued"
        PROCESSING = "processing"
        NEEDS_REVIEW = "needs_review"
        DONE = "done"
        FAILED = "failed"

    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="documents")
    uploader = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    file = models.FileField(upload_to="uploads/%Y/%m/")
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100, blank=True)
    size = models.PositiveBigIntegerField(default=0)
    sha256 = models.CharField(max_length=64, db_index=True)
    phash = models.CharField(max_length=16, blank=True)  # perceptual hash of page 1
    doc_type = models.CharField(max_length=30, default="invoice")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    error = models.TextField(blank=True)
    page_count = models.PositiveSmallIntegerField(default=0)
    progress = models.JSONField(default=dict, blank=True)  # {step: {status, detail, ts}}
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Page(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="pages")
    number = models.PositiveSmallIntegerField()
    image = models.ImageField(upload_to="pages/%Y/%m/")  # cleaned page image
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    words = models.JSONField(default=list)  # [{text, bbox:[x0,y0,x1,y1] normalised, conf, page}]

    class Meta:
        ordering = ["number"]
        constraints = [models.UniqueConstraint(fields=["document", "number"], name="uniq_page")]


class Region(models.Model):
    """Layout region on a page: found by the model, or drawn/fixed by a human (M8)."""

    page = models.ForeignKey(Page, on_delete=models.CASCADE, related_name="regions")
    cls = models.CharField(max_length=12)  # vendor | meta | table | totals | other
    bbox = models.JSONField()  # normalised [x0, y0, x1, y1]
    score = models.FloatField(default=1.0)
    source = models.CharField(max_length=10, default="model")  # model | human

    class Meta:
        ordering = ["id"]


class Extraction(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="extractions")
    version = models.PositiveIntegerField(default=1)
    data = models.JSONField(default=dict)  # raw schema output incl. line_items
    issues = models.JSONField(default=list)  # failed validation rules
    overall_confidence = models.FloatField(default=0.0)
    needs_review = models.BooleanField(default=False)
    provider = models.CharField(max_length=40, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-version"]
        constraints = [
            models.UniqueConstraint(fields=["document", "version"], name="uniq_extraction_version")
        ]


class FieldValue(models.Model):
    extraction = models.ForeignKey(Extraction, on_delete=models.CASCADE, related_name="fields")
    name = models.CharField(max_length=40)
    value = models.TextField(blank=True)  # model output, stringified
    confidence = models.FloatField(default=0.0)
    flags = models.JSONField(default=list)
    page = models.PositiveSmallIntegerField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)  # normalised [x0,y0,x1,y1]
    reviewed_value = models.TextField(null=True, blank=True)  # human correction (M3)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    box_edited = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["extraction", "name"], name="uniq_field")]


class AuditEvent(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="audit")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    action = models.CharField(max_length=40)  # field_edited | box_edited | approved
    detail = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class Vendor(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="vendors")
    name = models.CharField(max_length=200)
    ntn = models.CharField(max_length=30, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["workspace", "name"], name="uniq_vendor")]


class Invoice(models.Model):
    """Approved, query-friendly record (what analytics and the spending agent read)."""

    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="invoice")
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name="invoices")
    vendor = models.ForeignKey(
        Vendor, null=True, on_delete=models.SET_NULL, related_name="invoices"
    )
    ntn = models.CharField(max_length=30, blank=True)
    strn = models.CharField(max_length=30, blank=True)
    invoice_number = models.CharField(max_length=80, blank=True)
    invoice_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="PKR")
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    sales_tax = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    category = models.CharField(max_length=60, blank=True)
    approved_at = models.DateTimeField(auto_now=True)


class InvoiceLineItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    position = models.PositiveSmallIntegerField(default=0)
    description = models.CharField(max_length=300, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=3, null=True, blank=True)
    unit_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ["position"]
