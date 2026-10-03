# coding=utf-8
import decimal

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('basedata', '0007_material_drawing_file_material_model_file_and_more'),
        ('cnc', '0010_handoff'),
    ]

    operations = [
        migrations.AddField(
            model_name='workorder',
            name='stocked_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='\u5b8c\u5de5\u5165\u5e93\u65f6\u95f4'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='material_cost',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0'), max_digits=14, verbose_name='\u6750\u6599\u6210\u672c'),
        ),
        migrations.AddField(
            model_name='workorder',
            name='labor_cost',
            field=models.DecimalField(decimal_places=2, default=decimal.Decimal('0'), max_digits=14, verbose_name='\u5de5\u65f6\u6210\u672c'),
        ),
        migrations.CreateModel(
            name='WorkMaterial',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('need_qty', models.DecimalField(decimal_places=3, default=decimal.Decimal('0'), max_digits=12, verbose_name='\u9700\u7528\u6570\u91cf')),
                ('issued_qty', models.DecimalField(decimal_places=3, default=decimal.Decimal('0'), max_digits=12, verbose_name='\u5df2\u9886\u6570\u91cf')),
                ('note', models.CharField(blank=True, default='', max_length=120, verbose_name='\u8bf4\u660e')),
                ('material', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='basedata.material', verbose_name='\u7269\u6599')),
                ('work_order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='materials', to='cnc.workorder', verbose_name='\u5de5\u5355')),
            ],
            options={
                'verbose_name': '\u5de5\u5355\u7528\u6599',
                'verbose_name_plural': '\u5de5\u5355\u7528\u6599',
                'unique_together': {('work_order', 'material')},
            },
        ),
    ]
