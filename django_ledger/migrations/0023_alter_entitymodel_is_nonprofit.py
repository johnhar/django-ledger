# Generated by Django 5.1.6 on 2025-04-05 05:29

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_ledger', '0022_entitymodel_is_nonprofit'),
    ]

    operations = [
        migrations.AlterField(
            model_name='entitymodel',
            name='is_nonprofit',
            field=models.BooleanField(default=False, verbose_name='Is a Non-Profit'),
        ),
    ]
