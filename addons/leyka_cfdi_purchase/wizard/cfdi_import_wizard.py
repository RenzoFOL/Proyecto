import base64
import io
import zipfile

from odoo import fields, models, _
from odoo.exceptions import ValidationError


MAX_ARCHIVE_SIZE = 50 * 1024 * 1024
MAX_XML_FILES = 100


class LeykaCfdiImportWizard(models.TransientModel):
    _name = "leyka.cfdi.import.wizard"
    _description = "Importar CFDI XML o ZIP"

    upload = fields.Binary(
        string="Archivo XML o ZIP",
        required=True,
        attachment=False,
    )
    file_name = fields.Char(required=True)

    def _payloads(self):
        self.ensure_one()
        raw = base64.b64decode(self.upload or b"", validate=True)
        if len(raw) > MAX_ARCHIVE_SIZE:
            raise ValidationError(_("El archivo supera el límite de 50 MB."))
        if (self.file_name or "").lower().endswith(".xml"):
            return [(self.file_name, raw)]
        if not (self.file_name or "").lower().endswith(".zip"):
            raise ValidationError(_("Selecciona un archivo .xml o .zip."))
        try:
            archive = zipfile.ZipFile(io.BytesIO(raw))
        except zipfile.BadZipFile as error:
            raise ValidationError(_("El ZIP no es válido.")) from error
        members = [
            member
            for member in archive.infolist()
            if not member.is_dir() and member.filename.lower().endswith(".xml")
        ]
        if not members:
            raise ValidationError(_("El ZIP no contiene archivos XML."))
        if len(members) > MAX_XML_FILES:
            raise ValidationError(_("El ZIP contiene más de 100 XML."))
        if sum(member.file_size for member in members) > MAX_ARCHIVE_SIZE:
            raise ValidationError(_("Los XML descomprimidos superan 50 MB."))
        payloads = []
        for member in members:
            if member.file_size > 10 * 1024 * 1024:
                raise ValidationError(
                    _("El XML %s supera 10 MB.") % member.filename
                )
            payloads.append((member.filename.rsplit("/", 1)[-1], archive.read(member)))
        return payloads

    def action_import(self):
        documents = self.env["leyka.cfdi.purchase"]
        errors = []
        for file_name, payload in self._payloads():
            try:
                with self.env.cr.savepoint():
                    documents |= documents.import_xml_payload(payload, file_name)
            except Exception as error:
                errors.append("%s: %s" % (file_name, error))
        if not documents:
            raise ValidationError(
                _("No fue posible importar ningún CFDI:\n%s") % "\n".join(errors)
            )
        if errors:
            documents.write(
                {
                    "review_note": "\n".join(
                        filter(
                            None,
                            [
                                documents[0].review_note,
                                _("Archivos omitidos:"),
                                *errors,
                            ],
                        )
                    )
                }
            )
        return {
            "type": "ir.actions.act_window",
            "name": _("CFDI importados"),
            "res_model": "leyka.cfdi.purchase",
            "view_mode": "list,form",
            "domain": [("id", "in", documents.ids)],
            "target": "current",
        }
