# coding=utf-8
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('cnc', '0009_facesample_origin_alter_facesample_feature_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='Handoff',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(db_index=True, max_length=40, verbose_name='\u4e8c\u7ef4\u7801')),
                ('kind', models.CharField(default='info', max_length=12, verbose_name='\u7c7b\u578b')),
                ('place', models.CharField(blank=True, default='', max_length=40, verbose_name='\u5730\u70b9')),
                ('qty', models.CharField(blank=True, default='', max_length=20, verbose_name='\u6570\u91cf')),
                ('body', models.CharField(blank=True, default='', max_length=200, verbose_name='\u5185\u5bb9')),
                ('is_read', models.BooleanField(default=False, verbose_name='\u5df2\u8bfb')),
                ('created', models.DateTimeField(auto_now_add=True, verbose_name='\u65f6\u95f4')),
                ('receiver', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handoffs_in', to=settings.AUTH_USER_MODEL, verbose_name='\u63a5\u6536\u4eba')),
                ('sender', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='handoffs_out', to=settings.AUTH_USER_MODEL, verbose_name='\u53d1\u51fa\u4eba')),
            ],
            options={
                'verbose_name': '\u73b0\u573a\u4ea4\u63a5',
                'verbose_name_plural': '\u73b0\u573a\u4ea4\u63a5',
                'ordering': ['-id'],
            },
        ),
    ]
