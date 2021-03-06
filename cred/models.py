from django.db import models
from django.db.models import Q
from django.contrib import admin
from django.contrib.auth.models import User, Group
from django.forms import ModelForm, SelectMultiple

from tastypie.models import create_api_key

# Every time a user is saved, make sure they have an API key.
models.signals.post_save.connect(create_api_key, sender=User)


class Tag(models.Model):
    name = models.CharField(max_length=64)

    def __unicode__(self):
        return self.name


class TagForm(ModelForm):
    class Meta:
        model = Tag


class CredIcon(models.Model):
    name = models.CharField(max_length=50, unique=True)
    filename = models.CharField(max_length=50)
    xoffset = models.IntegerField(default=0)
    yoffset = models.IntegerField(default=0)

    def __unicode__(self):
        return self.name


class CredIconAdmin(admin.ModelAdmin):
    list_display = ('name', 'filename')


class SearchManager(models.Manager):
    def accessable(self, user, historical=False, deleted=False):
        usergroups = user.groups.all()
        qs = super(SearchManager, self).get_query_set()

        if not user.is_staff or not deleted:
            qs = qs.exclude(is_deleted=True, latest=None)

        if not historical:
            qs = qs.filter(latest=None)

        qs = qs.filter(Q(group__in=usergroups)
                     | Q(latest__group__in=usergroups))

        return qs


class Cred(models.Model):
    METADATA = ('description', 'group', 'tags', 'icon')
    objects = SearchManager()

    title = models.CharField(max_length=64)
    url = models.URLField(blank=True, null=True)
    username = models.CharField(max_length=250, blank=True, null=True)
    password = models.CharField(max_length=250)
    description = models.TextField(blank=True, null=True)
    group = models.ForeignKey(Group)
    tags = models.ManyToManyField(Tag, related_name='child_creds', blank=True, null=True, default=None)
    icon = models.ForeignKey(CredIcon, default=58)
    is_deleted = models.BooleanField(default=False)
    latest = models.ForeignKey('Cred', related_name='history', blank=True, null=True)
    created = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        try:
            old = Cred.objects.get(id=self.id)
            old.id = None
            old.latest = self
            old.save()
        except Cred.DoesNotExist:
            # This just means its new cred, ignore it
            pass
        super(Cred, self).save(*args, **kwargs)

    def delete(self):
        if not self.is_deleted:
            self.is_deleted = True
            self.save()
        else:
            super(Cred, self).delete()

    def on_changeq(self):
        return CredChangeQ.objects.filter(cred=self).exists()

    def is_accessable_by(self, user):
        # Staff can see anything
        if user.is_staff:
            return True

        # If its the latest and in your group you can see it
        if not self.is_deleted and self.latest is None and self.group in user.groups.all():
            return True

        # If the latest is in your group you can see it
        if not self.is_deleted and self.latest is not None and self.latest.group in user.groups.all():
            return True

        return False

    def __unicode__(self):
        return self.title


class CredForm(ModelForm):
    def __init__(self, requser, *args, **kwargs):
        super(CredForm, self).__init__(*args, **kwargs)
        self.fields['group'].queryset = Group.objects.filter(user=requser)

    class Meta:
        model = Cred
        exclude = ('is_deleted', 'latest')
        widgets = {
            'tags': SelectMultiple(attrs={'class': 'chzn-select'}),
        }


class CredAdmin(admin.ModelAdmin):
    list_display = ('title', 'username', 'group')


class CredAudit(models.Model):
    CREDADD = 'A'
    CREDCHANGE = 'C'
    CREDMETACHANGE = 'M'
    CREDVIEW = 'V'
    CREDPASSVIEW = 'P'
    CREDDELETE = 'D'
    CREDSCHEDCHANGE = 'S'
    CREDAUDITCHOICES = (
        (CREDADD, 'Credential Added'),
        (CREDCHANGE, 'Credential Change'),
        (CREDMETACHANGE, 'Credential Metadata change'),
        (CREDVIEW, 'Credential View'),
        (CREDDELETE, 'Credential Deleted'),
        (CREDSCHEDCHANGE, 'Scheduled For Change'),
        (CREDPASSVIEW, 'Credential Password View'),
    )

    audittype = models.CharField(max_length=1, choices=CREDAUDITCHOICES)
    cred = models.ForeignKey(Cred, related_name='logs')
    user = models.ForeignKey(User, related_name='credlogs')
    time = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = 'time'
        ordering = ('-time',)


class CredAuditAdmin(admin.ModelAdmin):
    list_display = ('audittype', 'user', 'cred', 'time')


class CredChangeQManager(models.Manager):
    def add_to_changeq(self, cred):
        return self.get_or_create(cred=cred)

    def for_user(self, user):
        return self.filter(cred__in=Cred.objects.accessable(user))


class CredChangeQ(models.Model):
    objects = CredChangeQManager()

    cred = models.ForeignKey(Cred, unique=True)
    time = models.DateTimeField(auto_now_add=True)


class CredChangeQAdmin(admin.ModelAdmin):
    list_display = ('cred', 'time')


admin.site.register(CredAudit, CredAuditAdmin)
admin.site.register(Cred, CredAdmin)
admin.site.register(CredIcon, CredIconAdmin)
admin.site.register(Tag)
admin.site.register(CredChangeQ, CredChangeQAdmin)
