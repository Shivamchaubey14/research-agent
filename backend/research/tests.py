from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from .models import Document, ResearchRun

User = get_user_model()


class AuthFlowTests(APITestCase):
    def test_register_then_obtain_token(self):
        resp = self.client.post(
            reverse("auth-register"),
            {"email": "a@example.com", "password": "Sup3rSecret!", "full_name": "A"},
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertNotIn("password", resp.data)

        resp = self.client.post(
            reverse("auth-token"),
            {"email": "a@example.com", "password": "Sup3rSecret!"},
            format="json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn("access", resp.data)
        self.assertIn("refresh", resp.data)

    def test_weak_password_rejected(self):
        resp = self.client.post(
            reverse("auth-register"),
            {"email": "b@example.com", "password": "123"},
            format="json",
        )
        self.assertEqual(resp.status_code, 400)

    def test_protected_endpoint_requires_token(self):
        self.assertEqual(self.client.get(reverse("run-list")).status_code, 401)


class RunTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("u@example.com", "Sup3rSecret!")
        self.other = User.objects.create_user("o@example.com", "Sup3rSecret!")
        self.client.force_authenticate(self.user)

    def test_submit_run_is_queued(self):
        resp = self.client.post(
            reverse("run-list"), {"question": "What is RAG?"}, format="json"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["status"], ResearchRun.Status.QUEUED)
        self.assertEqual(ResearchRun.objects.get(id=resp.data["id"]).user, self.user)

    def test_blank_question_rejected(self):
        resp = self.client.post(
            reverse("run-list"), {"question": "   "}, format="json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_user_cannot_see_others_run(self):
        run = ResearchRun.objects.create(user=self.other, question="secret")
        resp = self.client.get(reverse("run-detail", args=[run.id]))
        self.assertEqual(resp.status_code, 404)

    def test_cancel_run(self):
        run = ResearchRun.objects.create(user=self.user, question="q")
        resp = self.client.post(reverse("run-cancel", args=[run.id]))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], ResearchRun.Status.CANCELLED)

    def test_cannot_cancel_completed_run(self):
        run = ResearchRun.objects.create(
            user=self.user, question="q", status=ResearchRun.Status.COMPLETED
        )
        resp = self.client.post(reverse("run-cancel", args=[run.id]))
        self.assertEqual(resp.status_code, 409)


class DocumentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user("d@example.com", "Sup3rSecret!")
        self.client.force_authenticate(self.user)

    def test_upload_document(self):
        from django.core.files.uploadedfile import SimpleUploadedFile

        upload = SimpleUploadedFile("notes.txt", b"hello world", content_type="text/plain")
        resp = self.client.post(
            reverse("document-list"), {"file": upload}, format="multipart"
        )
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.data["filename"], "notes.txt")
        self.assertEqual(resp.data["status"], Document.Status.PROCESSING)
